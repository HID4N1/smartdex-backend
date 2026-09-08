from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chatbot.models import ChatMessage, Conversation
from apps.contact.models import ContactMessage
from apps.devis.models import DevisRequest
from core.compliance import cleanup_personal_data, retention_config


class PrivacyAcknowledgementTests(TestCase):
    def test_contact_submission_stores_privacy_notice_evidence_and_consent_default(self):
        response = APIClient().post(
            "/api/contact/",
            {
                "name": "Fatima Zahra",
                "email": "fatima@example.com",
                "subject": "Nouveau projet",
                "message": "Nous voulons creer un site web professionnel pour notre entreprise.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        contact = ContactMessage.objects.get()
        self.assertEqual(contact.processing_purpose, "contact_inquiry")
        self.assertEqual(contact.privacy_notice_version, "2026-09-08")
        self.assertIsNotNone(contact.privacy_notice_acknowledged_at)
        self.assertFalse(contact.marketing_consent)
        self.assertIsNone(contact.marketing_consented_at)

    def test_contact_marketing_consent_is_optional_and_timestamped_only_when_true(self):
        response = APIClient().post(
            "/api/contact/",
            {
                "name": "Fatima Zahra",
                "email": "fatima@example.com",
                "subject": "Nouveau projet",
                "message": "Nous voulons creer un site web professionnel pour notre entreprise.",
                "marketing_consent": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        contact = ContactMessage.objects.get()
        self.assertTrue(contact.marketing_consent)
        self.assertEqual(contact.marketing_consent_version, contact.privacy_notice_version)
        self.assertIsNotNone(contact.marketing_consented_at)

    def test_devis_submission_stores_privacy_notice_evidence_and_consent_default(self):
        response = APIClient().post(
            "/api/devis/requests/",
            {
                "description": "I need a booking website for my clinic.",
                "client_name": "Fatima Zahra",
                "client_email": "fatima@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        devis = DevisRequest.objects.get()
        self.assertEqual(devis.processing_purpose, "quote_request")
        self.assertEqual(devis.submission_source, "website_devis")
        self.assertEqual(devis.privacy_notice_version, "2026-09-08")
        self.assertIsNotNone(devis.privacy_notice_acknowledged_at)
        self.assertFalse(devis.marketing_consent)

    def test_chat_generated_devis_records_distinct_source(self):
        devis = DevisRequest.objects.create(
            description="Need a booking website.",
            submission_source="chatbot_generated",
        )

        self.assertEqual(devis.processing_purpose, "quote_request")
        self.assertEqual(devis.submission_source, "chatbot_generated")


class RetentionConfigurationTests(TestCase):
    @override_settings(
        SMARTDEX_PRIVACY_NOTICE_VERSION="cnpd-review",
        SMARTDEX_CONTACT_RETENTION_DAYS=400,
        SMARTDEX_ABANDONED_DEVIS_RETENTION_DAYS=300,
        SMARTDEX_COMPLETED_DEVIS_RETENTION_DAYS=2000,
        SMARTDEX_CHATBOT_RETENTION_DAYS=45,
        SMARTDEX_TEMP_PDF_RETENTION_HOURS=12,
    )
    def test_retention_config_loads_from_settings(self):
        self.assertEqual(
            retention_config(),
            {
                "privacy_notice_version": "cnpd-review",
                "contact_retention_days": 400,
                "abandoned_devis_retention_days": 300,
                "completed_devis_retention_days": 2000,
                "chatbot_retention_days": 45,
                "temp_pdf_retention_hours": 12,
            },
        )


@override_settings(
    SMARTDEX_CONTACT_RETENTION_DAYS=365,
    SMARTDEX_ABANDONED_DEVIS_RETENTION_DAYS=365,
    SMARTDEX_COMPLETED_DEVIS_RETENTION_DAYS=365,
    SMARTDEX_CHATBOT_RETENTION_DAYS=60,
    SMARTDEX_TEMP_PDF_RETENTION_HOURS=1000000,
)
class PersonalDataCleanupTests(TestCase):
    def make_contact(self, email, days_old):
        contact = ContactMessage.objects.create(
            name="Fatima Zahra",
            email=email,
            subject="Nouveau projet",
            message="Nous voulons creer un site web professionnel pour notre entreprise.",
        )
        ContactMessage.objects.filter(pk=contact.pk).update(
            created_at=timezone.now() - timedelta(days=days_old)
        )
        return contact

    def make_devis(self, email, status, days_old):
        devis = DevisRequest.objects.create(
            description="Need a booking website.",
            client_name="Fatima Zahra",
            client_email=email,
            status=status,
        )
        DevisRequest.objects.filter(pk=devis.pk).update(
            updated_at=timezone.now() - timedelta(days=days_old)
        )
        return devis

    def make_conversation(self, days_old):
        conversation = Conversation.objects.create(title="Support chat")
        ChatMessage.objects.create(
            conversation=conversation,
            role="user",
            content="I need a booking website. Contact me at fatima@example.com.",
        )
        Conversation.objects.filter(pk=conversation.pk).update(
            updated_at=timezone.now() - timedelta(days=days_old)
        )
        return conversation

    def test_dry_run_cleanup_does_not_delete_data(self):
        self.make_contact("old-contact@example.com", 500)
        self.make_devis("old-devis@example.com", "pending", 500)
        self.make_conversation(90)

        report = cleanup_personal_data(dry_run=True)

        self.assertEqual(report.contact_eligible, 1)
        self.assertEqual(report.abandoned_devis_eligible, 1)
        self.assertEqual(report.chatbot_eligible, 1)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(DevisRequest.objects.count(), 1)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_expired_eligible_records_are_deleted_and_non_expired_remain(self):
        old_contact = self.make_contact("old-contact@example.com", 500)
        fresh_contact = self.make_contact("fresh-contact@example.com", 10)
        old_devis = self.make_devis("old-devis@example.com", "failed", 500)
        fresh_devis = self.make_devis("fresh-devis@example.com", "pending", 10)
        old_conversation = self.make_conversation(90)
        fresh_conversation = self.make_conversation(10)

        report = cleanup_personal_data(dry_run=False)

        self.assertEqual(report.contact_deleted, 1)
        self.assertEqual(report.abandoned_devis_deleted, 1)
        self.assertEqual(report.chatbot_deleted, 1)
        self.assertFalse(ContactMessage.objects.filter(pk=old_contact.pk).exists())
        self.assertTrue(ContactMessage.objects.filter(pk=fresh_contact.pk).exists())
        self.assertFalse(DevisRequest.objects.filter(pk=old_devis.pk).exists())
        self.assertTrue(DevisRequest.objects.filter(pk=fresh_devis.pk).exists())
        self.assertFalse(Conversation.objects.filter(pk=old_conversation.pk).exists())
        self.assertTrue(Conversation.objects.filter(pk=fresh_conversation.pk).exists())

    def test_processed_devis_records_are_protected_from_automatic_cleanup(self):
        processed = self.make_devis("commercial@example.com", "processed", 500)

        report = cleanup_personal_data(dry_run=False)

        self.assertEqual(report.protected_devis_skipped, 1)
        self.assertEqual(report.abandoned_devis_deleted, 0)
        self.assertTrue(DevisRequest.objects.filter(pk=processed.pk).exists())

    def test_cleanup_command_output_does_not_expose_pii(self):
        self.make_contact("old-contact@example.com", 500)
        self.make_devis("old-devis@example.com", "pending", 500)
        output = StringIO()

        call_command("cleanup_personal_data", "--dry-run", stdout=output)

        text = output.getvalue()
        self.assertIn("mode=dry-run", text)
        self.assertIn("contact_eligible=1", text)
        self.assertIn("abandoned_devis_eligible=1", text)
        self.assertNotIn("old-contact@example.com", text)
        self.assertNotIn("old-devis@example.com", text)

    @patch("core.compliance._eligible_temp_pdf_paths")
    def test_expired_temp_pdfs_are_removed_without_database_pii(self, eligible_paths):
        pdf_path = Path("/tmp/devis_compliance_test.pdf")
        pdf_path.write_bytes(b"%PDF-1.4\n")
        eligible_paths.return_value = [pdf_path]

        report = cleanup_personal_data(dry_run=False)

        self.assertEqual(report.temp_pdf_eligible, 1)
        self.assertEqual(report.temp_pdf_deleted, 1)
        self.assertFalse(pdf_path.exists())

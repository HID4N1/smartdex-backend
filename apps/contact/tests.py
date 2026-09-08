from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.contact.models import ContactMessage
from core.utils.public_input_validation import CONTACT_MESSAGE_MAX_LENGTH


class ContactMessageAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.url = "/api/contact/"
        self.payload = {
            "name": "  Fatima Zahra  ",
            "email": "  fatima@example.com  ",
            "company": "  SmartDex Client  ",
            "project_type": "web",
            "budget": "5k-15k",
            "subject": "  Nouveau projet web  ",
            "message": "  Nous voulons créer un site web professionnel pour notre entreprise.  ",
        }

    def test_valid_contact_submission_returns_201(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json(), {"message": "Contact message received."})

    def test_valid_contact_submission_creates_row(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        message = ContactMessage.objects.get()
        self.assertEqual(message.name, "Fatima Zahra")
        self.assertEqual(message.email, "fatima@example.com")
        self.assertEqual(message.company, "SmartDex Client")
        self.assertEqual(message.subject, "Nouveau projet web")
        self.assertFalse(message.is_read)

    def test_missing_required_fields_returns_400(self):
        response = self.client.post(
            self.url,
            {"email": "fatima@example.com", "message": "Message long enough for validation."},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("name", response.json())
        self.assertIn("subject", response.json())

    def test_invalid_email_returns_400(self):
        payload = {**self.payload, "email": "not-an-email"}

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("email", response.json())

    def test_whitespace_message_returns_400(self):
        payload = {**self.payload, "message": "    \n\t   "}

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("message", response.json())
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_overlong_name_returns_400(self):
        payload = {**self.payload, "name": "F" * 101}

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("name", response.json())

    def test_overlong_message_returns_400(self):
        payload = {**self.payload, "message": "x" * (CONTACT_MESSAGE_MAX_LENGTH + 1)}

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("message", response.json())

    def test_multilingual_contact_content_is_accepted(self):
        payload = {
            **self.payload,
            "name": "ليلى Benali",
            "subject": "Projet multilingue",
            "message": "Bonjour, نحتاج منصة للزبناء avec paiement et notifications.",
        }

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 201, response.content)

    def test_public_submission_works_without_authentication(self):
        self.client.credentials()

        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, 201, response.content)

    def test_public_response_exposes_only_acknowledgement(self):
        response = self.client.post(self.url, self.payload, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(set(response.json().keys()), {"message"})

    def test_anonymous_get_list_is_not_available(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405, response.content)

    def test_anonymous_retrieve_is_not_available(self):
        ContactMessage.objects.create(
            name="Fatima Zahra",
            email="fatima@example.com",
            subject="Nouveau projet",
            message="Nous voulons creer un site web professionnel pour notre entreprise.",
        )

        response = self.client.get(f"{self.url}1/")

        self.assertEqual(response.status_code, 404, response.content)

    def test_anonymous_update_and_delete_are_not_available(self):
        put_response = self.client.put(self.url, self.payload, format="json")
        patch_response = self.client.patch(self.url, {"subject": "Changed"}, format="json")
        delete_response = self.client.delete(self.url)

        self.assertEqual(put_response.status_code, 405, put_response.content)
        self.assertEqual(patch_response.status_code, 405, patch_response.content)
        self.assertEqual(delete_response.status_code, 405, delete_response.content)

    def test_client_cannot_set_protected_fields(self):
        payload = {
            **self.payload,
            "is_read": True,
            "created_at": "2020-01-01T00:00:00Z",
        }

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        message = ContactMessage.objects.get()
        self.assertFalse(message.is_read)
        self.assertNotEqual(message.created_at.isoformat(), "2020-01-01T00:00:00+00:00")

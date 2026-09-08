from pathlib import Path
import tempfile
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.chatbot.models import ChatMessage, Conversation
from apps.contact.models import ContactMessage
from apps.devis.models import DevisRequest
from apps.devis.services.ai_input_builder import DevisAIInputBuilder
from apps.devis.services.devis_services import DevisService
from apps.devis.services.pdf_context_builder import PDFContextBuilder
from apps.devis.services.llm_service import LLMService
from core.utils.public_input_validation import (
    DEVIS_CHAT_MESSAGES_MAX_ITEMS,
    DEVIS_DESCRIPTION_MAX_LENGTH,
    DEVIS_FEATURES_MAX_ITEMS,
)


TEST_THROTTLE_SETTINGS = {
    "URL_FORMAT_OVERRIDE": None,
    "DEFAULT_THROTTLE_RATES": {
        "contact": "2/hour",
        "devis_create": "2/hour",
        "devis_generate": "2/hour",
        "chatbot": "2/hour",
    },
    "NUM_PROXIES": 0,
}


def processed_quote_result(devis_request):
    return {
        "request_id": devis_request.id,
        "status": "processed",
        "estimate": {
            "range_min": 1000,
            "range_max": 2000,
            "currency": "MAD",
            "cost_drivers": [],
            "recommendation": "Recommended scope",
        },
        "quote": {
            "included_groups": [],
            "optional_items": [],
            "recurring_items": [],
            "totals": {
                "included_min": 1000,
                "included_max": 2000,
                "optional_min": 0,
                "optional_max": 0,
                "recurring_min": 0,
                "recurring_max": 0,
                "grand_total_min": 1000,
                "grand_total_max": 2000,
            },
            "notes": [],
            "missing_information": [],
        },
        "pdf_url": f"/api/devis/requests/{devis_request.id}/generate/?format=pdf&token={devis_request.access_token}",
        "clarification_questions": [],
        "selected_features": [],
    }


class DevisRequestSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.create_url = "/api/devis/requests/"
        self.payload = {
            "description": "I need a booking website for my clinic.",
            "client_name": "Fatima Zahra",
            "client_email": "fatima@example.com",
            "client_phone": "+212600000000",
            "budget_range": "10k-20k",
            "timeline": "1 month",
            "project_type": "booking",
            "preferred_language": "fr",
            "features": ["booking", "payments"],
            "extra_hints": {"industry": "clinic"},
        }

    def tearDown(self):
        for devis_request in DevisRequest.objects.all():
            pdf_path = Path(tempfile.gettempdir()) / f"devis_{devis_request.id}.pdf"
            if pdf_path.exists():
                pdf_path.unlink()

    def create_devis_request(self, **overrides):
        return DevisRequest.objects.create(
            description=overrides.pop("description", "Need a showcase website."),
            client_name=overrides.pop("client_name", "Client"),
            client_email=overrides.pop("client_email", "client@example.com"),
            **overrides,
        )

    def test_creating_devis_generates_access_token(self):
        response = self.client.post(self.create_url, self.payload, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertIn("access_token", data)
        uuid.UUID(data["access_token"])

        devis_request = DevisRequest.objects.get(pk=data["id"])
        self.assertEqual(data["access_token"], str(devis_request.access_token))

    def test_valid_devis_request_succeeds(self):
        response = self.client.post(self.create_url, self.payload, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        devis_request = DevisRequest.objects.get(pk=response.json()["id"])
        self.assertEqual(devis_request.description, self.payload["description"])
        self.assertEqual(devis_request.features, self.payload["features"])
        self.assertEqual(devis_request.extra_hints, self.payload["extra_hints"])

    def test_devis_create_rejects_blank_description(self):
        response = self.client.post(
            self.create_url,
            {**self.payload, "description": "  \n\t  "},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("description", response.json())
        self.assertEqual(DevisRequest.objects.count(), 0)

    def test_devis_create_rejects_excessively_long_description(self):
        response = self.client.post(
            self.create_url,
            {**self.payload, "description": "x" * (DEVIS_DESCRIPTION_MAX_LENGTH + 1)},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("description", response.json())
        self.assertEqual(DevisRequest.objects.count(), 0)

    def test_devis_create_rejects_malformed_email(self):
        response = self.client.post(
            self.create_url,
            {**self.payload, "client_email": "not-an-email"},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("client_email", response.json())

    def test_devis_create_rejects_excessive_feature_count(self):
        response = self.client.post(
            self.create_url,
            {**self.payload, "features": [f"feature-{index}" for index in range(DEVIS_FEATURES_MAX_ITEMS + 1)]},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("features", response.json())

    def test_devis_create_rejects_nested_extra_hints(self):
        response = self.client.post(
            self.create_url,
            {**self.payload, "extra_hints": {"metadata": {"deep": "value"}}},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("extra_hints", response.json())

    def test_devis_create_rejects_negative_budget(self):
        response = self.client.post(
            self.create_url,
            {**self.payload, "budget_range": "-1000 MAD"},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("budget_range", response.json())

    def test_access_token_is_unique(self):
        first = self.create_devis_request(client_email="first@example.com")
        second = self.create_devis_request(client_email="second@example.com")

        self.assertNotEqual(first.access_token, second.access_token)

    def test_client_cannot_supply_or_override_access_token(self):
        supplied_token = uuid.uuid4()
        response = self.client.post(
            self.create_url,
            {**self.payload, "access_token": str(supplied_token), "status": "processed"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        devis_request = DevisRequest.objects.get(pk=response.json()["id"])
        self.assertNotEqual(devis_request.access_token, supplied_token)
        self.assertEqual(devis_request.status, "pending")

    def test_public_create_response_exposes_only_required_flow_fields(self):
        response = self.client.post(self.create_url, self.payload, format="json")

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(
            set(response.json().keys()),
            {"id", "access_token", "status", "message"},
        )

    def test_anonymous_list_retrieve_update_and_delete_are_not_available(self):
        devis_request = self.create_devis_request()

        list_response = self.client.get(self.create_url)
        retrieve_response = self.client.get(f"/api/devis/requests/{devis_request.id}/")
        put_response = self.client.put(
            f"/api/devis/requests/{devis_request.id}/",
            {"description": "Changed"},
            format="json",
        )
        patch_response = self.client.patch(
            f"/api/devis/requests/{devis_request.id}/",
            {"description": "Changed"},
            format="json",
        )
        delete_response = self.client.delete(f"/api/devis/requests/{devis_request.id}/")

        self.assertEqual(list_response.status_code, 405, list_response.content)
        self.assertEqual(retrieve_response.status_code, 404, retrieve_response.content)
        self.assertEqual(put_response.status_code, 404, put_response.content)
        self.assertEqual(patch_response.status_code, 404, patch_response.content)
        self.assertEqual(delete_response.status_code, 404, delete_response.content)

    def test_devis_create_rejects_unsupported_methods(self):
        self.assertEqual(self.client.get(self.create_url).status_code, 405)
        self.assertEqual(self.client.put(self.create_url, self.payload, format="json").status_code, 405)
        self.assertEqual(self.client.patch(self.create_url, self.payload, format="json").status_code, 405)
        self.assertEqual(self.client.delete(self.create_url).status_code, 405)

    @patch("apps.devis.views.DevisService")
    def test_anonymous_generate_with_correct_id_and_token_succeeds(self, service_class):
        devis_request = self.create_devis_request()
        service_class.return_value.generate_quote_from_request.return_value = processed_quote_result(devis_request)

        response = self.client.post(
            f"/api/devis/requests/{devis_request.id}/generate/?token={devis_request.access_token}",
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request_id"], devis_request.id)
        self.assertEqual(response.json()["access_token"], str(devis_request.access_token))
        service_class.return_value.generate_quote_from_request.assert_called_once_with(devis_request)

    @patch("apps.devis.views.DevisService")
    def test_anonymous_generate_with_wrong_token_fails(self, service_class):
        devis_request = self.create_devis_request()

        response = self.client.post(
            f"/api/devis/requests/{devis_request.id}/generate/?token={uuid.uuid4()}",
            format="json",
        )

        self.assertEqual(response.status_code, 404, response.content)
        service_class.return_value.generate_quote_from_request.assert_not_called()

    @patch("apps.devis.views.DevisService")
    def test_anonymous_generate_with_missing_token_fails(self, service_class):
        devis_request = self.create_devis_request()

        response = self.client.post(
            f"/api/devis/requests/{devis_request.id}/generate/",
            format="json",
        )

        self.assertEqual(response.status_code, 404, response.content)
        service_class.return_value.generate_quote_from_request.assert_not_called()

    @patch("apps.devis.views.DevisService")
    def test_anonymous_generate_with_another_devis_token_fails(self, service_class):
        devis_request = self.create_devis_request(client_email="first@example.com")
        other_request = self.create_devis_request(client_email="second@example.com")

        response = self.client.post(
            f"/api/devis/requests/{devis_request.id}/generate/?token={other_request.access_token}",
            format="json",
        )

        self.assertEqual(response.status_code, 404, response.content)
        service_class.return_value.generate_quote_from_request.assert_not_called()

    @patch("apps.devis.views.DevisService")
    def test_sequential_id_alone_cannot_access_pdf(self, service_class):
        devis_request = self.create_devis_request()

        response = self.client.post(
            f"/api/devis/requests/{devis_request.id}/generate/?format=pdf",
            format="json",
        )

        self.assertEqual(response.status_code, 404, response.content)
        service_class.return_value.generate_quote_from_request.assert_not_called()

    @patch("apps.devis.views.DevisService")
    def test_anonymous_pdf_with_correct_id_and_token_succeeds(self, service_class):
        devis_request = self.create_devis_request()
        pdf_path = Path(tempfile.gettempdir()) / f"devis_{devis_request.id}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nsecure devis\n")
        service_class.return_value.generate_quote_from_request.return_value = processed_quote_result(devis_request)

        response = self.client.post(
            f"/api/devis/requests/{devis_request.id}/generate/?format=pdf&token={devis_request.access_token}",
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        service_class.return_value.generate_quote_from_request.assert_called_once_with(devis_request)

    @patch("apps.devis.views.DevisService")
    def test_devis_generate_rejects_unsupported_methods(self, service_class):
        devis_request = self.create_devis_request()
        url = f"/api/devis/requests/{devis_request.id}/generate/?token={devis_request.access_token}"

        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.put(url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.patch(url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        service_class.return_value.generate_quote_from_request.assert_not_called()

    @patch("apps.devis.views.DevisService")
    def test_generate_from_chat_rejects_unsupported_methods(self, service_class):
        url = "/api/devis/generate-from-chat/"

        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.put(url, {"description": "Need a site"}, format="json").status_code, 405)
        self.assertEqual(self.client.patch(url, {"description": "Need a site"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        service_class.return_value.generate_quote_from_request.assert_not_called()

    @patch("apps.devis.views.DevisService")
    def test_generate_from_chat_rejects_excessive_messages_before_service(self, service_class):
        response = self.client.post(
            "/api/devis/generate-from-chat/",
            {
                "messages": [
                    {"role": "user", "content": f"Need feature {index}"}
                    for index in range(DEVIS_CHAT_MESSAGES_MAX_ITEMS + 1)
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("messages", response.json())
        service_class.return_value.create_request_from_description.assert_not_called()
        service_class.return_value.generate_quote_from_request.assert_not_called()

    @patch("apps.devis.views.DevisService")
    def test_generate_from_chat_rejects_blank_context_before_service(self, service_class):
        response = self.client.post(
            "/api/devis/generate-from-chat/",
            {"description": " ", "messages": [{"role": "assistant", "content": "Bonjour"}]},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        service_class.return_value.create_request_from_description.assert_not_called()
        service_class.return_value.generate_quote_from_request.assert_not_called()

    @patch("apps.devis.views.DevisService")
    def test_staff_can_generate_without_token(self, service_class):
        devis_request = self.create_devis_request()
        service_class.return_value.generate_quote_from_request.return_value = processed_quote_result(devis_request)
        user = get_user_model().objects.create_user(
            username="admin",
            password="password",
            is_staff=True,
        )
        self.client.force_authenticate(user=user)

        response = self.client.post(
            f"/api/devis/requests/{devis_request.id}/generate/",
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        service_class.return_value.generate_quote_from_request.assert_called_once_with(devis_request)


class PublicEndpointAuthorizationPostureTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_drf_default_permission_requires_authentication(self):
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"],
            ["rest_framework.permissions.IsAuthenticated"],
        )

    def test_production_renderers_are_json_only(self):
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"],
            ["rest_framework.renderers.JSONRenderer"],
        )

    def test_admin_remains_staff_login_protected(self):
        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_health_check_is_public_get_only(self):
        get_response = self.client.get("/api/health/")
        post_response = self.client.post("/api/health/", {}, format="json")

        self.assertEqual(get_response.status_code, 200, get_response.content)
        self.assertEqual(get_response.json(), {"status": "ok"})
        self.assertEqual(post_response.status_code, 405, post_response.content)


class RequestSizeHardeningTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.raise_request_exception = False

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=512)
    @patch("apps.chatbot.views.RAGChain")
    def test_oversized_json_body_is_rejected_before_chatbot_rag(self, rag_chain_class):
        response = self.client.post(
            "/api/chatbot/chat/",
            {"message": "x" * 600},
            format="json",
        )

        self.assertIn(response.status_code, {400, 413}, response.content)
        self.assertEqual(Conversation.objects.count(), 0)
        rag_chain_class.return_value.run.assert_not_called()


class DevisAIPrivacyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def create_private_devis_request(self):
        return DevisRequest.objects.create(
            description=(
                "Fatima Zahra needs a booking website for a clinic with online payments, "
                "WhatsApp reminders, budget 15000 MAD, and delivery within 1 month. "
                "Contact fatima@example.com or +212600000000. "
                "Address: 12 Rue Client, Casablanca. "
                "PDF link /api/devis/requests/7/generate/?format=pdf&token=123e4567-e89b-12d3-a456-426614174000"
            ),
            client_name="Fatima Zahra",
            client_email="fatima@example.com",
            client_phone="+212600000000",
            budget_range="15000 MAD",
            timeline="1 month",
            project_type="booking_system",
            preferred_language="fr",
            features=["payments", "notifications"],
            extra_hints={
                "industry": "clinic",
                "client_address": "12 Rue Client, Casablanca",
                "access_token": "secret-token",
            },
        )

    def assert_no_private_values(self, payload: str, devis_request: DevisRequest):
        self.assertNotIn(devis_request.client_name, payload)
        self.assertNotIn(devis_request.client_email, payload)
        self.assertNotIn(devis_request.client_phone, payload)
        self.assertNotIn(str(devis_request.access_token), payload)
        self.assertNotIn("123e4567-e89b-12d3-a456-426614174000", payload)
        self.assertNotIn("secret-token", payload)
        self.assertNotIn("12 Rue Client", payload)

    def test_ai_project_context_whitelists_quote_inputs_and_redacts_private_metadata(self):
        devis_request = self.create_private_devis_request()

        context = DevisAIInputBuilder.build_project_context(devis_request)
        serialized = str(context)

        self.assert_no_private_values(serialized, devis_request)
        self.assertIn("booking website", serialized)
        self.assertIn("payments", serialized)
        self.assertIn("notifications", serialized)
        self.assertIn("15000 MAD", serialized)
        self.assertEqual(context["extra_hints"], {"industry": "clinic"})

        devis_request.refresh_from_db()
        self.assertEqual(devis_request.client_name, "Fatima Zahra")
        self.assertEqual(devis_request.client_email, "fatima@example.com")
        self.assertEqual(devis_request.client_phone, "+212600000000")

    @patch("apps.devis.agents.orchestrator.DevisPDFGenerator.generate")
    @patch.object(LLMService, "generate_quote_text")
    @patch.object(LLMService, "extract_structured_json")
    def test_openai_devis_prompts_exclude_client_pii_but_keep_quote_context(
        self,
        extract_structured_json,
        generate_quote_text,
        pdf_generate,
    ):
        devis_request = self.create_private_devis_request()
        captured_prompts = {}
        captured_pdf_context = {}

        def fake_extract(*args, **kwargs):
            captured_prompts["requirement"] = kwargs["prompt"]
            return kwargs["fallback"]

        def fake_quote(*args, **kwargs):
            captured_prompts["quote"] = kwargs["prompt"]
            return kwargs["fallback"]

        def fake_pdf_generate(context, output_path):
            captured_pdf_context.update(context)
            return str(output_path)

        extract_structured_json.side_effect = fake_extract
        generate_quote_text.side_effect = fake_quote
        pdf_generate.side_effect = fake_pdf_generate

        result = DevisService().generate_quote_from_request(devis_request)

        self.assertEqual(result["status"], "processed")
        combined_prompt = "\n".join(captured_prompts.values())
        self.assert_no_private_values(combined_prompt, devis_request)
        self.assertIn("booking website", combined_prompt)
        self.assertIn("payments", combined_prompt)
        self.assertIn("notifications", combined_prompt)
        self.assertIn("15000 MAD", combined_prompt)
        self.assertNotIn("client_name", combined_prompt)
        self.assertNotIn("client_email", combined_prompt)
        self.assertNotIn("client_phone", combined_prompt)
        self.assertEqual(captured_pdf_context["client_name"], devis_request.client_name)
        self.assertEqual(captured_pdf_context["client_email"], devis_request.client_email)
        self.assertEqual(captured_pdf_context["client_phone"], devis_request.client_phone)

        devis_request.refresh_from_db()
        self.assertEqual(devis_request.client_name, "Fatima Zahra")
        self.assertEqual(devis_request.client_email, "fatima@example.com")
        self.assertEqual(devis_request.client_phone, "+212600000000")

    @patch("apps.devis.agents.orchestrator.DevisPDFGenerator.generate")
    @patch.object(LLMService, "generate_quote_text")
    @patch.object(LLMService, "extract_structured_json")
    def test_chatbot_to_devis_generation_does_not_reinject_contact_details_into_openai(
        self,
        extract_structured_json,
        generate_quote_text,
        pdf_generate,
    ):
        captured_prompts = {}

        def fake_extract(*args, **kwargs):
            captured_prompts["requirement"] = kwargs["prompt"]
            return kwargs["fallback"]

        def fake_quote(*args, **kwargs):
            captured_prompts["quote"] = kwargs["prompt"]
            return kwargs["fallback"]

        extract_structured_json.side_effect = fake_extract
        generate_quote_text.side_effect = fake_quote
        pdf_generate.side_effect = lambda _context, output_path: str(output_path)

        response = self.client.post(
            "/api/devis/generate-from-chat/",
            {
                "client_name": "Fatima Zahra",
                "client_email": "fatima@example.com",
                "client_phone": "+212600000000",
                "preferred_language": "fr",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Je suis Fatima Zahra, fatima@example.com, +212600000000. "
                            "Je veux un booking website pour une clinique avec payments et notifications."
                        ),
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        devis_request = DevisRequest.objects.get(pk=response.json()["request_id"])
        combined_prompt = "\n".join(captured_prompts.values())
        self.assert_no_private_values(combined_prompt, devis_request)
        self.assertIn("booking website", combined_prompt)
        self.assertIn("payments", combined_prompt)
        self.assertIn("notifications", combined_prompt)
        self.assertEqual(devis_request.client_name, "Fatima Zahra")
        self.assertEqual(devis_request.client_email, "fatima@example.com")
        self.assertEqual(devis_request.client_phone, "+212600000000")

    def test_pdf_context_keeps_local_client_contact_information(self):
        devis_request = self.create_private_devis_request()
        context = PDFContextBuilder.build(
            devis_request,
            {
                "estimate": {"range_min": 1000, "range_max": 2000, "currency": "MAD"},
                "quote": {"totals": {}, "included_groups": []},
            },
        )

        self.assertEqual(context["client_name"], "Fatima Zahra")
        self.assertEqual(context["client_email"], "fatima@example.com")
        self.assertEqual(context["client_phone"], "+212600000000")


@override_settings(REST_FRAMEWORK=TEST_THROTTLE_SETTINGS)
class PublicEndpointThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.original_throttle_rates = SimpleRateThrottle.THROTTLE_RATES
        SimpleRateThrottle.THROTTLE_RATES = TEST_THROTTLE_SETTINGS["DEFAULT_THROTTLE_RATES"]
        self.client = APIClient()
        self.contact_payload = {
            "name": "Fatima Zahra",
            "email": "fatima@example.com",
            "company": "SmartDex Client",
            "project_type": "web",
            "budget": "5k-15k",
            "subject": "Nouveau projet web",
            "message": "Nous voulons creer un site web professionnel pour notre entreprise.",
        }
        self.devis_payload = {
            "description": "I need a booking website for a clinic.",
            "client_name": "Fatima Zahra",
            "client_email": "fatima@example.com",
        }

    def tearDown(self):
        SimpleRateThrottle.THROTTLE_RATES = self.original_throttle_rates
        cache.clear()

    def create_devis_request(self):
        return DevisRequest.objects.create(
            description="Need a showcase website.",
            client_name="Client",
            client_email="client@example.com",
        )

    def chatbot_result(self):
        return {
            "query": "bonjour",
            "rewritten_query": None,
            "intent": "greeting",
            "state": "wait_for_project",
            "answer": "Bonjour.",
            "sources": [],
            "structured_state": {"current_state": "wait_for_project"},
            "runtime_trace": {},
        }

    def test_contact_requests_allowed_below_limit(self):
        first = self.client.post("/api/contact/", self.contact_payload, format="json")
        second = self.client.post("/api/contact/", self.contact_payload, format="json")

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(ContactMessage.objects.count(), 2)

    def test_contact_returns_429_after_limit(self):
        self.client.post("/api/contact/", self.contact_payload, format="json")
        self.client.post("/api/contact/", self.contact_payload, format="json")

        response = self.client.post("/api/contact/", self.contact_payload, format="json")

        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(ContactMessage.objects.count(), 2)

    def test_devis_creation_returns_429_after_limit(self):
        self.client.post("/api/devis/requests/", self.devis_payload, format="json")
        self.client.post("/api/devis/requests/", self.devis_payload, format="json")

        response = self.client.post("/api/devis/requests/", self.devis_payload, format="json")

        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(DevisRequest.objects.count(), 2)

    @patch("apps.devis.views.DevisService")
    def test_devis_generation_returns_429_and_skips_service_after_limit(self, service_class):
        devis_request = self.create_devis_request()
        service_class.return_value.generate_quote_from_request.return_value = processed_quote_result(devis_request)
        url = f"/api/devis/requests/{devis_request.id}/generate/?token={devis_request.access_token}"

        self.client.post(url, format="json")
        self.client.post(url, format="json")
        response = self.client.post(url, format="json")

        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(service_class.return_value.generate_quote_from_request.call_count, 2)

    @patch("apps.chatbot.views.RAGChain")
    def test_chatbot_returns_429_and_skips_rag_after_limit(self, rag_chain_class):
        rag_chain_class.return_value.run.return_value = self.chatbot_result()

        self.client.post("/api/chatbot/chat/", {"message": "bonjour"}, format="json")
        self.client.post("/api/chatbot/chat/", {"message": "bonjour"}, format="json")
        conversations_before_throttled_request = Conversation.objects.count()
        messages_before_throttled_request = ChatMessage.objects.count()

        response = self.client.post("/api/chatbot/chat/", {"message": "bonjour"}, format="json")

        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(rag_chain_class.return_value.run.call_count, 2)
        self.assertEqual(Conversation.objects.count(), conversations_before_throttled_request)
        self.assertEqual(ChatMessage.objects.count(), messages_before_throttled_request)

    def test_throttling_scopes_are_independent(self):
        self.client.post("/api/contact/", self.contact_payload, format="json")
        self.client.post("/api/contact/", self.contact_payload, format="json")
        blocked_contact = self.client.post("/api/contact/", self.contact_payload, format="json")

        devis_response = self.client.post("/api/devis/requests/", self.devis_payload, format="json")

        self.assertEqual(blocked_contact.status_code, 429, blocked_contact.content)
        self.assertEqual(devis_response.status_code, 201, devis_response.content)

    @patch("apps.devis.views.DevisService")
    def test_authenticated_staff_uses_user_bucket_not_anonymous_ip_bucket(self, service_class):
        devis_request = self.create_devis_request()
        service_class.return_value.generate_quote_from_request.return_value = processed_quote_result(devis_request)
        url = f"/api/devis/requests/{devis_request.id}/generate/?token={devis_request.access_token}"
        self.client.post(url, format="json")
        self.client.post(url, format="json")
        anonymous_blocked = self.client.post(url, format="json")

        user = get_user_model().objects.create_user(
            username="staff",
            password="password",
            is_staff=True,
        )
        self.client.force_authenticate(user=user)
        staff_response = self.client.post(
            f"/api/devis/requests/{devis_request.id}/generate/",
            format="json",
        )

        self.assertEqual(anonymous_blocked.status_code, 429, anonymous_blocked.content)
        self.assertEqual(staff_response.status_code, 200, staff_response.content)
        self.assertEqual(service_class.return_value.generate_quote_from_request.call_count, 3)

    @override_settings(
        REST_FRAMEWORK={
            **TEST_THROTTLE_SETTINGS,
            "NUM_PROXIES": 1,
        }
    )
    def test_configured_proxy_depth_uses_single_trusted_forwarded_client(self):
        first = self.client.post(
            "/api/contact/",
            self.contact_payload,
            format="json",
            REMOTE_ADDR="10.0.0.10",
            HTTP_X_FORWARDED_FOR="198.51.100.10",
        )
        second = self.client.post(
            "/api/contact/",
            self.contact_payload,
            format="json",
            REMOTE_ADDR="10.0.0.10",
            HTTP_X_FORWARDED_FOR="198.51.100.10",
        )
        blocked_same_client = self.client.post(
            "/api/contact/",
            self.contact_payload,
            format="json",
            REMOTE_ADDR="10.0.0.10",
            HTTP_X_FORWARDED_FOR="198.51.100.10",
        )
        different_forwarded_client = self.client.post(
            "/api/contact/",
            self.contact_payload,
            format="json",
            REMOTE_ADDR="10.0.0.10",
            HTTP_X_FORWARDED_FOR="198.51.100.11",
        )

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(blocked_same_client.status_code, 429, blocked_same_client.content)
        self.assertEqual(different_forwarded_client.status_code, 201, different_forwarded_client.content)

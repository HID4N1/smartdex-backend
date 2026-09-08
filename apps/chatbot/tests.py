from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.chatbot.services.business_logic import BusinessLogicEngine, QualificationNotAllowed
from apps.chatbot.services.state_machine import ConversationState, SalesStateMachine
from apps.chatbot.services.validation import ResponseValidator


class ChatbotBusinessLogicTests(SimpleTestCase):
    def test_detects_service_package_and_pricing_without_llm(self):
        decision = BusinessLogicEngine().analyze(
            "I need a booking website with payments and WhatsApp notifications"
        )

        self.assertEqual(decision.facts["project_type"], "booking_system")
        self.assertEqual(decision.recommended_service, "Booking and Reservation System")
        self.assertTrue(decision.recommended_package)
        self.assertTrue(decision.pricing)
        self.assertEqual(decision.pricing["currency"], "MAD")

    def test_state_blocks_pricing_when_scope_is_missing(self):
        decision = BusinessLogicEngine().analyze("How much does it cost?")
        state = SalesStateMachine().choose_state(
            query="How much does it cost?",
            facts=decision.facts,
            history=[],
        )

        self.assertEqual(state, ConversationState.WAIT_FOR_PROJECT)

    def test_state_allows_pricing_when_scope_is_known(self):
        engine = BusinessLogicEngine()
        history = [
            {
                "role": "user",
                "content": "I run a clinic and need a booking system with reminders.",
            }
        ]
        decision = engine.analyze("How much does it cost?", history=history)
        state = SalesStateMachine().choose_state(
            query="How much does it cost?",
            facts=decision.facts,
            history=history,
        )

        self.assertEqual(state, ConversationState.PRICING)

    def test_structured_state_corrects_showcase_conversation(self):
        engine = BusinessLogicEngine()
        state = {}

        state = engine.update_structured_state(query="vitrine", previous_state=state)[0]
        self.assertEqual(state["project_type"], "showcase_website")
        self.assertIsNone(state["industry"])

        state = engine.update_structured_state(query="Cosmétiques", previous_state=state)[0]
        self.assertEqual(state["industry"], "cosmetics")
        self.assertEqual(state["project_type"], "showcase_website")

        state = engine.update_structured_state(query="vente en ligne", previous_state=state)[0]
        self.assertIn("online_sales", state["requested_features"])
        self.assertNotEqual(state["service_family"], "ai_solution")
        self.assertIn(state["project_type"], {"ecommerce", "showcase_with_catalog"})

        state = engine.update_structured_state(query="non un simple site web vitrine", previous_state=state)[0]
        self.assertEqual(state["project_type"], "showcase_website")
        self.assertEqual(state["service_family"], "website_development")
        self.assertNotIn("online_sales", state["requested_features"])
        self.assertIn("online_sales", state["rejected_features"])
        self.assertIn("ai_solution", state["rejected_features"])

        state = engine.update_structured_state(query="non je veux seulement une simple vitrine", previous_state=state)[0]
        self.assertEqual(state["project_type"], "showcase_website")
        self.assertNotIn("online_sales", state["requested_features"])
        self.assertNotEqual(state["service_family"], "ai_solution")

        state = engine.update_structured_state(query="SA", previous_state=state)[0]
        self.assertEqual(state["legal_structure"], "SA")

        state = engine.update_structured_state(query="SARL", previous_state=state)[0]
        self.assertEqual(state["legal_structure"], "SARL")
        self.assertNotEqual(state["legal_structure"], "SA")

    def test_car_rental_industry_normalization_and_trace(self):
        engine = BusinessLogicEngine()
        previous_state = {
            "has_active_project": True,
            "project_type": "website",
            "requested_solution": "website",
            "last_asked_field": "industry",
        }
        trace = engine.trace_message_processing(
            query="location de voiture",
            previous_state=previous_state,
        )
        state = trace["recomputed_state"]

        self.assertEqual(trace["incoming"], "location de voiture")
        self.assertEqual(trace["extracted_entities"]["industry"], "car_rental")
        self.assertIsNone(trace["state_before"]["industry"])
        self.assertEqual(trace["merge_result"]["industry"], "car_rental")
        self.assertEqual(state["industry"], "car_rental")
        self.assertIn("industry", trace["completed_fields"])
        self.assertNotIn("industry", trace["missing_fields"])
        self.assertNotEqual(trace["selected_next_field"], "industry")

    def test_car_rental_industry_synonyms_normalize_to_same_value(self):
        engine = BusinessLogicEngine()
        phrases = [
            "location de voiture",
            "location automobile",
            "agence de location",
            "loueur automobile",
            "location de véhicules",
            "Auto Rental",
            "car rental",
        ]

        for phrase in phrases:
            with self.subTest(phrase=phrase):
                state = engine.update_structured_state(
                    query=phrase,
                    previous_state={
                        "has_active_project": True,
                        "project_type": "website",
                        "requested_solution": "website",
                    },
                )[0]
                self.assertEqual(state["industry"], "car_rental")
                self.assertIn("industry", state["completed_fields"])
                self.assertNotIn("industry", state["missing_relevant_fields"])

    def test_qualification_selector_raises_before_project_intent(self):
        engine = BusinessLogicEngine()

        with self.assertRaises(QualificationNotAllowed):
            engine.select_missing_relevant_fields(engine.initial_state())


class ChatbotResponseValidatorTests(SimpleTestCase):
    def test_rejects_pricing_when_not_allowed(self):
        result = ResponseValidator().validate(
            answer="This would cost around 10000 MAD. What features do you need?",
            decision={},
            allow_pricing=False,
        )

        self.assertFalse(result.valid)
        self.assertIn("pricing mentioned before pricing is allowed", result.reasons)

    def test_rejects_more_than_one_question(self):
        result = ResponseValidator().validate(
            answer="SmartDex can help with that. What business do you run? What budget do you have?",
            decision={},
            allow_pricing=True,
        )

        self.assertFalse(result.valid)
        self.assertIn("more than one question", result.reasons)


class ChatbotAPIRegressionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_greeting_stays_in_wait_for_project_without_qualification(self):
        client = APIClient()
        response = client.post("/api/chatbot/chat/", {"message": "bonjour"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()

        self.assertEqual(data["answer"], "Bonjour ! Comment puis-je vous aider aujourd’hui ?")
        self.assertEqual(data["state"], ConversationState.WAIT_FOR_PROJECT)
        self.assertEqual(data["structured_state"]["current_state"], ConversationState.WAIT_FOR_PROJECT)
        self.assertFalse(data["structured_state"]["has_active_project"])
        self.assertEqual(data["structured_state"]["missing_relevant_fields"], [])
        self.assertEqual(data["runtime_trace"]["detected_intent"], "greeting")
        self.assertEqual(data["runtime_trace"]["selected_handler"], "greeting_handler")
        self.assertFalse(data["runtime_trace"]["qualification_selector_called"])
        self.assertEqual(data["runtime_trace"]["final_state"], ConversationState.WAIT_FOR_PROJECT)
        self.assertNotIn("secteur", data["answer"].lower())
        self.assertNotIn("activité", data["answer"].lower())
        self.assertNotIn("statut juridique", data["answer"].lower())

    def test_greeting_then_thanks_remains_wait_for_project(self):
        client = APIClient()
        first = client.post("/api/chatbot/chat/", {"message": "Bonjour"}, format="json").json()
        second = client.post(
            "/api/chatbot/chat/",
            {"message": "Merci", "conversation_id": first["conversation_id"]},
            format="json",
        )
        self.assertEqual(second.status_code, 200, second.content)
        data = second.json()

        self.assertEqual(data["state"], ConversationState.WAIT_FOR_PROJECT)
        self.assertEqual(data["structured_state"]["current_state"], ConversationState.WAIT_FOR_PROJECT)
        self.assertFalse(data["structured_state"]["has_active_project"])
        self.assertNotIn("secteur", data["answer"].lower())
        self.assertNotIn("budget", data["answer"].lower())

    def test_greeting_then_site_web_enters_discovery(self):
        client = APIClient()
        first = client.post("/api/chatbot/chat/", {"message": "Bonjour"}, format="json").json()
        second = client.post(
            "/api/chatbot/chat/",
            {"message": "Je veux un site web.", "conversation_id": first["conversation_id"]},
            format="json",
        )
        self.assertEqual(second.status_code, 200, second.content)
        data = second.json()

        self.assertEqual(data["state"], ConversationState.DISCOVERY)
        self.assertEqual(data["structured_state"]["current_state"], ConversationState.DISCOVERY)
        self.assertTrue(data["structured_state"]["has_active_project"])
        self.assertEqual(data["structured_state"]["project_type"], "website")
        self.assertEqual(data["answer"], "Très bien.\n\nQuel est votre secteur d'activité ?")

    def test_greeting_then_services_question_remains_wait_for_project(self):
        client = APIClient()
        first = client.post("/api/chatbot/chat/", {"message": "Bonjour"}, format="json").json()
        second = client.post(
            "/api/chatbot/chat/",
            {"message": "Quels services proposez-vous ?", "conversation_id": first["conversation_id"]},
            format="json",
        )
        self.assertEqual(second.status_code, 200, second.content)
        data = second.json()

        self.assertEqual(data["state"], ConversationState.WAIT_FOR_PROJECT)
        self.assertEqual(data["structured_state"]["current_state"], ConversationState.WAIT_FOR_PROJECT)
        self.assertFalse(data["structured_state"]["has_active_project"])
        self.assertIn("SmartDex propose", data["answer"])
        self.assertNotIn("secteur", data["answer"].lower())

    def test_greeting_then_erp_enters_discovery_without_pricing_or_recommendation(self):
        client = APIClient()
        first = client.post("/api/chatbot/chat/", {"message": "Bonjour"}, format="json").json()
        second = client.post(
            "/api/chatbot/chat/",
            {"message": "Je veux un ERP.", "conversation_id": first["conversation_id"]},
            format="json",
        )
        self.assertEqual(second.status_code, 200, second.content)
        data = second.json()

        self.assertEqual(data["state"], ConversationState.DISCOVERY)
        self.assertEqual(data["structured_state"]["current_state"], ConversationState.DISCOVERY)
        self.assertEqual(data["structured_state"]["project_type"], "erp")
        self.assertTrue(data["structured_state"]["has_active_project"])
        self.assertLessEqual(data["answer"].count("?"), 1)
        self.assertNotIn("mad", data["answer"].lower())
        self.assertNotIn("recommand", data["answer"].lower())

    def test_car_rental_answer_does_not_repeat_industry_question(self):
        client = APIClient()
        first = client.post("/api/chatbot/chat/", {"message": "Bonjour"}, format="json").json()
        second = client.post(
            "/api/chatbot/chat/",
            {"message": "Je veux un site web.", "conversation_id": first["conversation_id"]},
            format="json",
        ).json()
        self.assertEqual(second["answer"], "Très bien.\n\nQuel est votre secteur d'activité ?")

        third_response = client.post(
            "/api/chatbot/chat/",
            {"message": "location de voiture", "conversation_id": first["conversation_id"]},
            format="json",
        )
        self.assertEqual(third_response.status_code, 200, third_response.content)
        third = third_response.json()
        state = third["structured_state"]

        self.assertEqual(state["industry"], "car_rental")
        self.assertIn("industry", state["completed_fields"])
        self.assertNotIn("industry", state["missing_relevant_fields"])
        self.assertNotEqual(state["missing_relevant_fields"][0], "industry")
        self.assertNotIn("secteur", third["answer"].lower())
        self.assertNotIn("type d'activité", third["answer"].lower())

    def test_new_conversation_starts_with_fresh_structured_state(self):
        client = APIClient()
        first = client.post("/api/chatbot/chat/", {"message": "Bonjour"}, format="json").json()
        client.post(
            "/api/chatbot/chat/",
            {"message": "Je veux un site web.", "conversation_id": first["conversation_id"]},
            format="json",
        )

        fresh = client.post("/api/chatbot/chat/", {"message": "Bonjour"}, format="json").json()
        self.assertNotEqual(fresh["conversation_id"], first["conversation_id"])
        self.assertFalse(fresh["structured_state"]["has_active_project"])
        self.assertEqual(fresh["structured_state"]["current_state"], ConversationState.WAIT_FOR_PROJECT)
        self.assertIsNone(fresh["structured_state"]["project_type"])
        self.assertEqual(fresh["structured_state"]["missing_relevant_fields"], [])

    def test_exact_showcase_state_conversation_through_api(self):
        client = APIClient()
        conversation_id = None
        turns = [
            "Je veux un site web pour mon activité",
            "vitrine",
            "Cosmétiques",
            "vente en ligne",
            "non un simple site web vitrine",
            "non je veux seulement une simple vitrine",
            "SA",
            "SARL",
        ]
        answers = []
        states = []

        for message in turns:
            payload = {"message": message}
            if conversation_id:
                payload["conversation_id"] = conversation_id

            response = client.post("/api/chatbot/chat/", payload, format="json")
            self.assertEqual(response.status_code, 200, response.content)
            data = response.json()
            conversation_id = data["conversation_id"]
            answers.append(data["answer"])
            states.append(data["structured_state"])

            self.assertLessEqual(data["answer"].count("?"), 1)
            self.assertNotIn("intelligence artificielle", data["answer"].lower())
            self.assertNotIn("ce système", data["answer"].lower())

        after_vitrine = states[1]
        self.assertEqual(after_vitrine["project_type"], "showcase_website")
        self.assertIsNone(after_vitrine["industry"])

        after_cosmetics = states[2]
        self.assertEqual(after_cosmetics["industry"], "cosmetics")
        self.assertEqual(after_cosmetics["project_type"], "showcase_website")

        after_online_sales = states[3]
        self.assertIn("online_sales", after_online_sales["requested_features"])
        self.assertNotEqual(after_online_sales["service_family"], "ai_solution")
        self.assertIn(after_online_sales["project_type"], {"ecommerce", "showcase_with_catalog"})

        after_first_correction = states[4]
        self.assertEqual(after_first_correction["project_type"], "showcase_website")
        self.assertEqual(after_first_correction["service_family"], "website_development")
        self.assertNotIn("online_sales", after_first_correction["requested_features"])
        self.assertIn("online_sales", after_first_correction["rejected_features"])

        after_second_correction = states[5]
        self.assertEqual(after_second_correction["project_type"], "showcase_website")
        self.assertNotIn("online_sales", after_second_correction["requested_features"])
        self.assertNotEqual(after_second_correction["service_family"], "ai_solution")

        after_sa = states[6]
        self.assertEqual(after_sa["legal_structure"], "SA")
        self.assertNotIn("type d'entreprise", answers[6].lower())

        final_state = states[7]
        self.assertEqual(final_state["language"], "fr")
        self.assertEqual(final_state["industry"], "cosmetics")
        self.assertEqual(final_state["project_type"], "showcase_website")
        self.assertEqual(final_state["service_family"], "website_development")
        self.assertEqual(final_state["requested_features"], [])
        self.assertEqual(final_state["legal_structure"], "SARL")
        self.assertNotIn("online_sales", final_state["requested_features"])
        self.assertIn("legal_structure", final_state["completed_fields"])
        self.assertNotIn("type d'entreprise", answers[7].lower())

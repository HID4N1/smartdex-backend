from django.test import SimpleTestCase

from apps.chatbot.services.business_logic import BusinessLogicEngine
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

        self.assertEqual(state, ConversationState.QUALIFICATION)

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

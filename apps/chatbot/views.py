from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.chatbot.models import Conversation, ChatMessage
from apps.chatbot.serializers import ChatRequestSerializer, ConversationSerializer
from apps.chatbot.services.business_logic import BusinessLogicEngine
from core.ai.rag.chain import RAGChain


class ChatbotAPIView(APIView):
    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = serializer.validated_data["message"]
        conversation_id = serializer.validated_data.get("conversation_id")
        is_new_conversation = False

        if conversation_id:
            conversation = Conversation.objects.filter(id=conversation_id).first()
            if not conversation:
                return Response(
                    {"detail": "Conversation not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            conversation = Conversation.objects.create(
                title="New conversation",
                structured_state=BusinessLogicEngine().initial_state(),
            )
            is_new_conversation = True

        ChatMessage.objects.create(
            conversation=conversation,
            role="user",
            content=message,
        )

        history = list(
            conversation.messages.order_by("created_at").values("role", "content")
        )

        rag = RAGChain()
        result = rag.run(
            message,
            history=history[:-1],
            structured_state=conversation.structured_state,
            conversation_id=str(conversation.id),
            is_new_conversation=is_new_conversation,
        )
        conversation.structured_state = result.get("structured_state") or conversation.structured_state
        conversation.save(update_fields=["structured_state", "updated_at"])

        assistant_message = ChatMessage.objects.create(
            conversation=conversation,
            role="assistant",
            content=result["answer"],
        )

        return Response({
            "conversation_id": str(conversation.id),
            "message_id": assistant_message.id,
            "query": result["query"],
            "rewritten_query": result.get("rewritten_query"),
            "intent": result["intent"],
            "state": result.get("state"),
            "answer": result["answer"],
            "sources": result["sources"],
            "structured_state": conversation.structured_state,
            "runtime_trace": result.get("runtime_trace"),
        })

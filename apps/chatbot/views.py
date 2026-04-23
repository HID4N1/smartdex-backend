from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.chatbot.models import Conversation, ChatMessage
from apps.chatbot.serializers import ChatRequestSerializer, ConversationSerializer
from core.ai.rag.chain import RAGChain


class ChatbotAPIView(APIView):
    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = serializer.validated_data["message"]
        conversation_id = serializer.validated_data.get("conversation_id")

        if conversation_id:
            conversation = Conversation.objects.filter(id=conversation_id).first()
            if not conversation:
                return Response(
                    {"detail": "Conversation not found."},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            conversation = Conversation.objects.create(title="New conversation")

        ChatMessage.objects.create(
            conversation=conversation,
            role="user",
            content=message,
        )

        history = list(
            conversation.messages.order_by("created_at").values("role", "content")
        )

        rag = RAGChain()
        result = rag.run(message, history=history[:-1])

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
            "answer": result["answer"],
            "sources": result["sources"],
        })
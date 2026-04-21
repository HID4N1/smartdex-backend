import logging

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .serializers import ChatRequestSerializer
from core.ai.rag.chain import RAGChain

logger = logging.getLogger(__name__)


def get_chain() -> RAGChain:
    return RAGChain()


@api_view(["POST"])
def chat(request):
    serializer = ChatRequestSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {
                "message": "",
                "intent": "unknown",
                "answer": "",
                "sources": [],
                "error": "Invalid request.",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    message = serializer.validated_data["message"]

    try:
        chain = get_chain()
        result = chain.run(message)

        return Response(
            {
                "message": message,
                "intent": result.get("intent", "general"),
                "answer": result.get("answer", ""),
                "sources": result.get("sources", []),
                "error": None,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.exception("Chatbot request failed: %s", e)

        return Response(
            {
                "message": message,
                "intent": "unknown",
                "answer": "",
                "sources": [],
                "error": "Unable to process the request right now.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
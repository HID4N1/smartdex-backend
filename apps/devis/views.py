from pathlib import Path
import tempfile
import logging

from django.http import FileResponse
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.devis.models import DevisRequest
from apps.devis.serializers import (
    DevisRequestCreateSerializer,
    GenerateDevisFromChatSerializer,
    GeneratedQuoteResponseSerializer,
)
from apps.devis.services.devis_services import DevisService

logger = logging.getLogger(__name__)


def _build_description_from_messages(messages: list[dict]) -> str:
    user_messages = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = (message.get("content") or "").strip()
        if content:
            user_messages.append(content)

    if not user_messages:
        return ""

    summary = " ".join(user_messages)
    return f"Client conversation summary: {summary}"


class DevisRequestCreateView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = DevisRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        devis_request = serializer.save()

        return Response(
            {
                "id": devis_request.id,
                "status": devis_request.status,
                "message": "Devis request created successfully.",
            },
            status=status.HTTP_201_CREATED,
        )


class DevisRequestGenerateQuoteView(APIView):
    def post(self, request, pk: int, *args, **kwargs):
        devis_request = get_object_or_404(DevisRequest, pk=pk)
        service = DevisService()

        result = service.generate_quote_from_request(devis_request)
        output_format = request.query_params.get("format", "json").lower()

        if output_format == "pdf" and result.get("status") == "processed":
            pdf_path = Path(tempfile.gettempdir()) / f"devis_{devis_request.id}.pdf"
            if pdf_path.exists():
                return FileResponse(
                    open(pdf_path, "rb"),
                    content_type="application/pdf",
                    as_attachment=True,
                    filename=f"devis_{devis_request.id}.pdf",
                )

        if result.get("status") == "processed":
            response_serializer = GeneratedQuoteResponseSerializer(result)
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        http_status = status.HTTP_200_OK if result.get("status") == "needs_clarification" else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response(result, status=http_status)


class GenerateDevisFromChatView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = GenerateDevisFromChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        description = (data.get("description") or "").strip()
        if not description:
            description = _build_description_from_messages(data.get("messages", []))

        if not description:
            return Response(
                {
                    "request_id": None,
                    "status": "failed",
                    "detail": "Could not generate devis. Please provide a description or user messages.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = DevisService()
        devis_request = None

        try:
            devis_request = service.create_request_from_description(
                description=description,
                client_name=data.get("client_name", ""),
                client_email=data.get("client_email", ""),
                client_phone=data.get("client_phone", ""),
                preferred_language=data.get("preferred_language", ""),
            )
            result = service.generate_quote_from_request(devis_request)
        except Exception:
            logger.exception("Unexpected error while generating devis from chat context.")
            return Response(
                {
                    "request_id": None,
                    "status": "failed",
                    "detail": "Could not generate devis. Please try again.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if result.get("status") == "processed":
            return Response(
                {
                    "request_id": result.get("request_id"),
                    "status": "processed",
                    "estimate": result.get("estimate"),
                    "quote": result.get("quote"),
                    "pdf_url": result.get("pdf_url"),
                    "clarification_questions": result.get("clarification_questions", []),
                    "selected_features": result.get("selected_features", []),
                },
                status=status.HTTP_200_OK,
            )

        if result.get("status") == "needs_clarification":
            return Response(
                {
                    "request_id": result.get("request_id"),
                    "status": "needs_clarification",
                    "estimate": None,
                    "quote": None,
                    "pdf_url": None,
                    "clarification_questions": result.get("clarification_questions", []),
                    "selected_features": result.get("selected_features", []),
                },
                status=status.HTTP_200_OK,
            )

        logger.error(
            "Devis generation from chat failed for request_id=%s",
            result.get("request_id") or getattr(devis_request, "id", None),
        )
        return Response(
            {
                "request_id": result.get("request_id") or getattr(devis_request, "id", None),
                "status": "failed",
                "detail": "Could not generate devis. Please try again.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

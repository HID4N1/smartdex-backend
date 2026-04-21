from pathlib import Path
import tempfile

from django.http import FileResponse
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.devis.models import DevisRequest
from apps.devis.serializers import (
    DevisRequestCreateSerializer,
    GeneratedQuoteResponseSerializer,
)
from apps.devis.services.devis_services import DevisService
from apps.devis.services.pdf_context_builder import PDFContextBuilder
from apps.devis.services.pdf_generator import DevisPDFGenerator


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

        try:
            result = service.generate_quote_from_request(devis_request)

            response_payload = {
                "request_id": devis_request.id,
                "status": getattr(devis_request, "status", "processed"),
                "estimate": result.get("estimate", {}),
                "quote": result.get("quote", {}),
            }

            output_format = request.query_params.get("format", "json").lower()

            if output_format == "pdf":
                pdf_context = PDFContextBuilder.build(devis_request, response_payload)

                temp_dir = Path(tempfile.gettempdir())
                pdf_path = temp_dir / f"devis_{devis_request.id}.pdf"

                DevisPDFGenerator().generate(pdf_context, pdf_path)

                return FileResponse(
                    open(pdf_path, "rb"),
                    content_type="application/pdf",
                    as_attachment=True,
                    filename=f"devis_{devis_request.id}.pdf",
                )

            response_serializer = GeneratedQuoteResponseSerializer(response_payload)
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except Exception:
            devis_request.status = "failed"
            devis_request.save(update_fields=["status", "updated_at"])
            raise
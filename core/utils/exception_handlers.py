from django.core.exceptions import RequestDataTooBig
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from core.ai.provider import AIProviderError


def public_exception_handler(exc, context):
    if isinstance(exc, AIProviderError):
        return Response(
            {
                "detail": exc.public_message,
                "error": "ai_dependency_unavailable",
            },
            status=exc.public_status_code,
        )
    if isinstance(exc, RequestDataTooBig):
        return Response(
            {"detail": "Request body is too large."},
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    return exception_handler(exc, context)

import logging

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from core.ai.provider import AIProviderError


logger = logging.getLogger(__name__)


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
    response = exception_handler(exc, context)
    if response is not None or settings.DEBUG:
        return response

    request = context.get("request") if context else None
    logger.error(
        "unhandled_api_exception error_type=%s method=%s path=%s",
        type(exc).__name__,
        getattr(request, "method", "unknown"),
        getattr(request, "path", "unknown"),
    )
    return Response(
        {"detail": "An internal error occurred."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

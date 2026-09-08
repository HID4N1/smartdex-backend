from django.core.exceptions import RequestDataTooBig
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def public_exception_handler(exc, context):
    if isinstance(exc, RequestDataTooBig):
        return Response(
            {"detail": "Request body is too large."},
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    return exception_handler(exc, context)

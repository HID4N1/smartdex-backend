from django.conf import settings
from django.http import JsonResponse


class RequestBodySizeLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        limit = getattr(settings, "DATA_UPLOAD_MAX_MEMORY_SIZE", None)
        content_length = request.META.get("CONTENT_LENGTH")
        if limit and content_length:
            try:
                body_size = int(content_length)
            except ValueError:
                body_size = 0
            if body_size > limit:
                return JsonResponse(
                    {"detail": "Request body is too large."},
                    status=413,
                )
        return self.get_response(request)


class SensitiveResponseCacheMiddleware:
    """Prevent shared or browser caches from retaining admin and API responses."""

    protected_prefixes = ("/admin/", "/api/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(self.protected_prefixes):
            response["Cache-Control"] = "no-store"
        return response

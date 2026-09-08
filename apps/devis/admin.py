from django.contrib import admin
from .models import DevisRequest


# Register your models here.

class DevisRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "client_name", "client_email", "status", "submission_source", "created_at")
    list_filter = ("status", "submission_source", "marketing_consent", "created_at")
    search_fields = ("client_name", "client_email", "description")
    readonly_fields = (
        "access_token",
        "processing_purpose",
        "submission_source",
        "privacy_notice_acknowledged_at",
        "marketing_consented_at",
        "created_at",
        "updated_at",
    )

admin.site.register(DevisRequest, DevisRequestAdmin)


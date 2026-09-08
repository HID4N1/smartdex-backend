from django.contrib import admin

from apps.contact.models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "company", "processing_purpose", "created_at", "is_read")
    list_filter = ("is_read", "processing_purpose", "marketing_consent", "created_at", "project_type", "budget")
    search_fields = ("name", "email", "company", "subject", "message")
    readonly_fields = (
        "created_at",
        "processing_purpose",
        "privacy_notice_acknowledged_at",
        "marketing_consented_at",
    )

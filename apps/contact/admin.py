from django.contrib import admin

from apps.contact.models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "company", "created_at", "is_read")
    list_filter = ("is_read", "created_at", "project_type", "budget")
    search_fields = ("name", "email", "company", "subject", "message")
    readonly_fields = ("created_at",)

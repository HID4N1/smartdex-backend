from django.contrib import admin
from .models import DevisRequest


# Register your models here.

class DevisRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "client_name", "client_email", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("client_name", "client_email", "description")

admin.site.register(DevisRequest, DevisRequestAdmin)



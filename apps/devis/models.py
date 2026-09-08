import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def current_privacy_notice_version():
    return settings.SMARTDEX_PRIVACY_NOTICE_VERSION


class DevisRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processed", "Processed"),
        ("failed", "Failed"),
    ]

    description = models.TextField()
    client_name = models.CharField(max_length=255, blank=True)
    client_email = models.EmailField(blank=True)
    client_phone = models.CharField(max_length=50, blank=True)

    budget_range = models.CharField(max_length=100, blank=True)
    timeline = models.CharField(max_length=100, blank=True)
    project_type = models.CharField(max_length=100, blank=True)
    preferred_language = models.CharField(max_length=10, blank=True)

    features = models.JSONField(default=list, blank=True)
    extra_hints = models.JSONField(default=dict, blank=True)
    processing_purpose = models.CharField(
        max_length=50,
        default="quote_request",
        editable=False,
    )
    submission_source = models.CharField(
        max_length=50,
        default="website_devis",
        editable=False,
    )
    privacy_notice_version = models.CharField(
        max_length=50,
        default=current_privacy_notice_version,
    )
    privacy_notice_acknowledged_at = models.DateTimeField(default=timezone.now)
    marketing_consent = models.BooleanField(default=False)
    marketing_consent_version = models.CharField(max_length=50, blank=True)
    marketing_consented_at = models.DateTimeField(null=True, blank=True)

    access_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        label = self.client_name or self.client_email or f"Request #{self.pk}"
        return f"DevisRequest<{label}>"

    def save(self, *args, **kwargs):
        if self.marketing_consent:
            if not self.marketing_consented_at:
                self.marketing_consented_at = timezone.now()
            if not self.marketing_consent_version:
                self.marketing_consent_version = self.privacy_notice_version
        else:
            self.marketing_consented_at = None
            self.marketing_consent_version = ""
        super().save(*args, **kwargs)

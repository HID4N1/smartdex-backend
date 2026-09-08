from django.db import models
from django.conf import settings
from django.utils import timezone


def current_privacy_notice_version():
    return settings.SMARTDEX_PRIVACY_NOTICE_VERSION


class ContactMessage(models.Model):
    PROJECT_TYPE_CHOICES = [
        ("web", "Développement Web"),
        ("mobile", "Application Mobile"),
        ("saas", "Plateforme SaaS"),
        ("ecommerce", "E-commerce"),
        ("integration", "Intégration & API"),
        ("other", "Autre"),
    ]

    BUDGET_CHOICES = [
        ("<5k", "Moins de 5 000 MAD"),
        ("5k-15k", "5 000 MAD - 15 000 MAD"),
        ("15k-50k", "15 000 MAD - 50 000 MAD"),
        ("50k+", "Plus de 50 000 MAD"),
        ("discuss", "À discuter"),
    ]

    name = models.CharField(max_length=150)
    email = models.EmailField(max_length=254)
    company = models.CharField(max_length=150, blank=True)
    project_type = models.CharField(
        max_length=50,
        choices=PROJECT_TYPE_CHOICES,
        blank=True,
    )
    budget = models.CharField(max_length=50, choices=BUDGET_CHOICES, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField(max_length=2000)
    processing_purpose = models.CharField(
        max_length=50,
        default="contact_inquiry",
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
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ContactMessage<{self.name} - {self.subject}>"

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

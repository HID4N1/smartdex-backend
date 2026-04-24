from django.db import models


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

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        label = self.client_name or self.client_email or f"Request #{self.pk}"
        return f"DevisRequest<{label}>"

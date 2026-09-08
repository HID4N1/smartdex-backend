from django.db import models


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
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ContactMessage<{self.name} - {self.subject}>"

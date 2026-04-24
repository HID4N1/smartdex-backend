from django.urls import path
from .views import (
    DevisRequestCreateView,
    DevisRequestGenerateQuoteView,
    GenerateDevisFromChatView,
)

urlpatterns = [
    path("requests/", DevisRequestCreateView.as_view(), name="devis-request-create"),
    path("requests/<int:pk>/generate/", DevisRequestGenerateQuoteView.as_view(), name="devis-generate"),
    path("generate-from-chat/", GenerateDevisFromChatView.as_view(), name="generate-devis-from-chat"),
]

from django.urls import path
from .views import DevisRequestCreateView, DevisRequestGenerateQuoteView

urlpatterns = [
    path("requests/", DevisRequestCreateView.as_view(), name="devis-request-create"),
    path("requests/<int:pk>/generate/", DevisRequestGenerateQuoteView.as_view(), name="devis-generate"),
]
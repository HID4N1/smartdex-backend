from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import tempfile

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.chatbot.models import Conversation
from apps.contact.models import ContactMessage
from apps.devis.models import DevisRequest


@dataclass
class CleanupReport:
    contact_eligible: int = 0
    contact_deleted: int = 0
    abandoned_devis_eligible: int = 0
    abandoned_devis_deleted: int = 0
    protected_devis_skipped: int = 0
    chatbot_eligible: int = 0
    chatbot_deleted: int = 0
    temp_pdf_eligible: int = 0
    temp_pdf_deleted: int = 0


def retention_config() -> dict:
    return {
        "privacy_notice_version": settings.SMARTDEX_PRIVACY_NOTICE_VERSION,
        "contact_retention_days": settings.SMARTDEX_CONTACT_RETENTION_DAYS,
        "abandoned_devis_retention_days": settings.SMARTDEX_ABANDONED_DEVIS_RETENTION_DAYS,
        "completed_devis_retention_days": settings.SMARTDEX_COMPLETED_DEVIS_RETENTION_DAYS,
        "chatbot_retention_days": settings.SMARTDEX_CHATBOT_RETENTION_DAYS,
        "temp_pdf_retention_hours": settings.SMARTDEX_TEMP_PDF_RETENTION_HOURS,
    }


def delete_contact_inquiry(contact_id: int, *, dry_run: bool = False) -> int:
    queryset = ContactMessage.objects.filter(pk=contact_id)
    if dry_run:
        return queryset.count()
    deleted, _ = queryset.delete()
    return deleted


def delete_abandoned_devis(devis_id: int, *, dry_run: bool = False) -> int:
    queryset = DevisRequest.objects.filter(pk=devis_id, status__in=["pending", "failed"])
    if dry_run:
        return queryset.count()
    deleted, _ = queryset.delete()
    return deleted


def delete_chatbot_conversation(conversation_id, *, dry_run: bool = False) -> int:
    queryset = Conversation.objects.filter(pk=conversation_id)
    if dry_run:
        return queryset.count()
    deleted, _ = queryset.delete()
    return deleted


def cleanup_personal_data(*, dry_run: bool = True) -> CleanupReport:
    now = timezone.now()
    report = CleanupReport()

    contact_cutoff = now - timedelta(days=settings.SMARTDEX_CONTACT_RETENTION_DAYS)
    abandoned_devis_cutoff = now - timedelta(days=settings.SMARTDEX_ABANDONED_DEVIS_RETENTION_DAYS)
    completed_devis_cutoff = now - timedelta(days=settings.SMARTDEX_COMPLETED_DEVIS_RETENTION_DAYS)
    chatbot_cutoff = now - timedelta(days=settings.SMARTDEX_CHATBOT_RETENTION_DAYS)

    contact_queryset = ContactMessage.objects.filter(created_at__lt=contact_cutoff)
    abandoned_devis_queryset = DevisRequest.objects.filter(
        status__in=["pending", "failed"],
        updated_at__lt=abandoned_devis_cutoff,
    )
    protected_devis_queryset = DevisRequest.objects.filter(
        status="processed",
        updated_at__lt=completed_devis_cutoff,
    )
    chatbot_queryset = Conversation.objects.filter(updated_at__lt=chatbot_cutoff)

    report.contact_eligible = contact_queryset.count()
    report.abandoned_devis_eligible = abandoned_devis_queryset.count()
    report.protected_devis_skipped = protected_devis_queryset.count()
    report.chatbot_eligible = chatbot_queryset.count()

    report.temp_pdf_eligible = len(_eligible_temp_pdf_paths(now=now))

    if dry_run:
        return report

    with transaction.atomic():
        report.contact_deleted, _ = contact_queryset.delete()
        report.abandoned_devis_deleted, _ = abandoned_devis_queryset.delete()
        report.chatbot_deleted = report.chatbot_eligible
        chatbot_queryset.delete()

    for path in _eligible_temp_pdf_paths(now=now):
        try:
            path.unlink()
            report.temp_pdf_deleted += 1
        except FileNotFoundError:
            continue

    return report


def _eligible_temp_pdf_paths(*, now) -> list[Path]:
    max_age_seconds = settings.SMARTDEX_TEMP_PDF_RETENTION_HOURS * 60 * 60
    if max_age_seconds < 0:
        return []

    now_timestamp = now.timestamp()
    temp_dir = Path(tempfile.gettempdir())
    eligible = []
    for path in temp_dir.glob("devis_*.pdf"):
        try:
            age_seconds = now_timestamp - path.stat().st_mtime
        except FileNotFoundError:
            continue
        if age_seconds > max_age_seconds:
            eligible.append(path)
    return eligible

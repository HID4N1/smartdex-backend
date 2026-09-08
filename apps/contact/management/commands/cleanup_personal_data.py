from django.core.management.base import BaseCommand

from core.compliance import cleanup_personal_data, retention_config


class Command(BaseCommand):
    help = "Clean expired SmartDex website personal data without printing PII."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report eligible record counts without deleting data.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        config = retention_config()
        report = cleanup_personal_data(dry_run=dry_run)

        self.stdout.write(f"mode={'dry-run' if dry_run else 'delete'}")
        self.stdout.write(
            "retention="
            f"contact_days:{config['contact_retention_days']},"
            f"abandoned_devis_days:{config['abandoned_devis_retention_days']},"
            f"completed_devis_days:{config['completed_devis_retention_days']},"
            f"chatbot_days:{config['chatbot_retention_days']},"
            f"temp_pdf_hours:{config['temp_pdf_retention_hours']}"
        )
        self.stdout.write(f"contact_eligible={report.contact_eligible}")
        self.stdout.write(f"contact_deleted={report.contact_deleted}")
        self.stdout.write(f"abandoned_devis_eligible={report.abandoned_devis_eligible}")
        self.stdout.write(f"abandoned_devis_deleted={report.abandoned_devis_deleted}")
        self.stdout.write(f"protected_devis_skipped={report.protected_devis_skipped}")
        self.stdout.write(f"chatbot_eligible={report.chatbot_eligible}")
        self.stdout.write(f"chatbot_deleted={report.chatbot_deleted}")
        self.stdout.write(f"temp_pdf_eligible={report.temp_pdf_eligible}")
        self.stdout.write(f"temp_pdf_deleted={report.temp_pdf_deleted}")

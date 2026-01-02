from django.core.management.base import BaseCommand

from core.services import run_data_quality_checks


class Command(BaseCommand):
    help = "Run integrity checks and print unresolved alerts."

    def handle(self, *args, **options):
        alerts = list(run_data_quality_checks())
        if not alerts:
            self.stdout.write(self.style.SUCCESS("No data quality issues detected."))
            return

        self.stdout.write(self.style.WARNING(f"Detected {len(alerts)} data quality issue(s):"))
        for alert in alerts:
            self.stdout.write(
                f"- [{alert.severity.upper()}] {alert.category}: {alert.message}"
            )

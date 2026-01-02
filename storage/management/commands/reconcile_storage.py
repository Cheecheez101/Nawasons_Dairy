"""Management command to reconcile cold storage and inventory quantities."""
from django.core.management.base import BaseCommand

from storage.services import reconcile_storage_records


class Command(BaseCommand):
    help = "Compares InventoryItem current_quantity against ColdStorageInventory records by SKU and optionally fixes issues."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist fixes (delete zero-quantity lots). Default is dry-run.",
        )

    def handle(self, *args, **options):
        dry_run = not options["apply"]
        report = reconcile_storage_records(dry_run=dry_run)

        missing_links = report["missing_links"]
        mismatches = report.get("mismatched_skus", [])
        lots_removed = report["lots_removed"]

        if missing_links:
            self.stdout.write(self.style.WARNING("Inventory items missing batch linkage:"))
            for entry in missing_links:
                self.stdout.write(f"  - {entry['sku']}: {entry['name']}")
        else:
            self.stdout.write(self.style.SUCCESS("All inventory items have batch IDs."))

        if mismatches:
            self.stdout.write(self.style.WARNING("Quantity mismatches detected (by SKU):"))
            for mismatch in mismatches:
                self.stdout.write(
                    f"  - {mismatch['sku']}: inventory={mismatch['inventory_qty']} vs storage={mismatch['storage_qty']}"
                )
        else:
            self.stdout.write(self.style.SUCCESS("No quantity mismatches detected."))

        if lots_removed:
            if dry_run:
                self.stdout.write(
                    self.style.NOTICE(
                        f"Lots that would be removed (dry-run): {', '.join(map(str, lots_removed)) or 'none'}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Removed zero-quantity lots: {', '.join(map(str, lots_removed)) or 'none'}"
                    )
                )
        else:
            self.stdout.write(self.style.SUCCESS("No zero-quantity lots found."))

        if dry_run:
            self.stdout.write(self.style.NOTICE("Dry-run complete. Re-run with --apply to persist deletions."))
        else:
            self.stdout.write(self.style.SUCCESS("Reconciliation complete."))
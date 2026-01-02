"""Management command to sync InventoryItem quantities from ColdStorageInventory."""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum, Min
from django.utils import timezone

from inventory.models import InventoryItem, InventoryTransaction
from production.models import ProductionBatch
from storage.models import ColdStorageInventory


class Command(BaseCommand):
    help = (
        "Syncs InventoryItem.current_quantity to match ColdStorageInventory totals by SKU. "
        "Also links batch_id and expiry_date where possible."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist changes. Default is dry-run.",
        )

    def handle(self, *args, **options):
        dry_run = not options["apply"]
        today = timezone.now().date()

        # Build storage totals keyed by SKU (aggregating across all batches)
        storage_data = (
            ColdStorageInventory.objects
            .select_related("production_batch")
            .values("production_batch__sku", "production_batch__product_type")
            .annotate(
                total_qty=Sum("quantity"),
                earliest_expiry=Min("expiry_date"),
            )
        )

        sku_totals = {}
        for entry in storage_data:
            sku = entry["production_batch__sku"]
            if not sku:
                continue
            sku_totals[sku] = {
                "quantity": Decimal(entry["total_qty"] or 0),
                "expiry": entry["earliest_expiry"],
                "product_type": entry["production_batch__product_type"],
            }

        # Get most recent batch_id per SKU
        for sku in sku_totals:
            latest_batch = (
                ProductionBatch.objects
                .filter(sku=sku)
                .order_by("-produced_at")
                .first()
            )
            if latest_batch:
                sku_totals[sku]["batch_id"] = latest_batch.id
                sku_totals[sku]["product_name"] = latest_batch.get_product_type_display()
            else:
                sku_totals[sku]["batch_id"] = None
                sku_totals[sku]["product_name"] = sku

        updates = []
        creates = []

        for sku, data in sku_totals.items():
            try:
                item = InventoryItem.objects.get(sku=sku)
            except InventoryItem.DoesNotExist:
                creates.append({
                    "sku": sku,
                    "name": data["product_name"],
                    "batch_id": data["batch_id"],
                    "quantity": data["quantity"],
                    "expiry": data["expiry"],
                    "product_type": data["product_type"],
                })
                continue

            old_qty = Decimal(item.current_quantity or 0)
            new_qty = data["quantity"]
            delta = new_qty - old_qty
            if delta == 0 and item.batch_id == data["batch_id"]:
                continue
            updates.append({
                "item": item,
                "old_qty": old_qty,
                "new_qty": new_qty,
                "delta": delta,
                "batch_id": data["batch_id"],
                "expiry": data["expiry"],
            })

        if creates:
            self.stdout.write(self.style.WARNING("Inventory items to create:"))
            for c in creates:
                self.stdout.write(f"  + {c['sku']}: {c['name']} qty={c['quantity']}")
        else:
            self.stdout.write(self.style.SUCCESS("No new inventory items needed."))

        if updates:
            self.stdout.write(self.style.WARNING("Inventory items to update:"))
            for u in updates:
                self.stdout.write(
                    f"  ~ {u['item'].sku}: {u['old_qty']} -> {u['new_qty']} (delta {u['delta']:+})"
                )
        else:
            self.stdout.write(self.style.SUCCESS("All existing items already in sync."))

        if dry_run:
            self.stdout.write(self.style.NOTICE("Dry-run complete. Re-run with --apply to persist."))
            return

        # Apply creates
        for c in creates:
            item = InventoryItem.objects.create(
                name=c["name"],
                sku=c["sku"],
                unit="UNIT",
                current_quantity=c["quantity"],
                product_category=c["product_type"],
                is_processed=True,
                batch_id=c["batch_id"],
                expiry_date=c["expiry"],
                last_restocked=today,
            )
            InventoryTransaction.objects.create(
                item=item,
                quantity=c["quantity"],
                reason="Initial sync from storage",
                batch_id=c["batch_id"],
            )
            self.stdout.write(self.style.SUCCESS(f"Created {item.sku}"))

        # Apply updates
        for u in updates:
            item = u["item"]
            item.current_quantity = u["new_qty"]
            item.batch_id = u["batch_id"]
            if u["expiry"]:
                item.expiry_date = u["expiry"]
            item.last_restocked = today
            item.save(update_fields=["current_quantity", "batch_id", "expiry_date", "last_restocked"])
            if u["delta"] != 0:
                InventoryTransaction.objects.create(
                    item=item,
                    quantity=u["delta"],
                    reason="Sync from storage reconciliation",
                    batch_id=u["batch_id"],
                )
            self.stdout.write(self.style.SUCCESS(f"Updated {item.sku}"))

        self.stdout.write(self.style.SUCCESS("Sync complete."))

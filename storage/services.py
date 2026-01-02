"""Utility helpers for synchronizing cold storage with downstream operations."""
from collections import defaultdict
from decimal import Decimal
from typing import Dict, Iterable, Tuple

from django.db import transaction
from django.utils import timezone

from inventory.models import InventoryItem

from .models import ColdStorageInventory


def _status_for_expiry(expiry_date):
    today = timezone.now().date()
    if expiry_date < today:
        return "expired"
    if (expiry_date - today).days <= 3:
        return "near_expiry"
    return "in_storage"


def adjust_storage_for_inventory_item(inventory_item, quantity_delta):
    """Apply a quantity delta to the storage record tied to the item's batch.

    Negative deltas represent product leaving storage (sales/dispatch).
    Positive deltas return stock to storage (sale reversal, restock).
    """
    batch_id = getattr(inventory_item, "batch_id", None)
    if not batch_id:
        return False

    delta = quantity_delta if isinstance(quantity_delta, Decimal) else Decimal(str(quantity_delta))
    if delta == 0:
        return False

    with transaction.atomic():
        try:
            record = (
                ColdStorageInventory.objects
                .select_for_update()
                .get(production_batch_id=batch_id)
            )
        except ColdStorageInventory.DoesNotExist:
            return False

        new_quantity = record.quantity + delta
        if new_quantity <= 0:
            record.delete()
            return True

        record.quantity = new_quantity
        record.last_restocked = timezone.now()
        record.status = _status_for_expiry(record.expiry_date)
        record.save(update_fields=["quantity", "last_restocked", "status"])
        return True


def iter_inventory_with_batches() -> Iterable[Tuple[InventoryItem, Tuple[int, Decimal]]]:
    """Yield inventory items and a tuple(batch_id, quantity)."""
    for item in InventoryItem.objects.exclude(batch_id__isnull=True):
        yield item, (item.batch_id, item.current_quantity or Decimal("0"))


def aggregate_storage_by_sku() -> Dict[str, Decimal]:
    """Return SKU -> total quantity currently in storage across all batches."""
    from production.models import ProductionBatch
    totals: Dict[str, Decimal] = defaultdict(Decimal)
    for lot in ColdStorageInventory.objects.select_related("production_batch"):
        batch = lot.production_batch
        if not batch:
            continue
        sku = getattr(batch, "sku", None)
        if sku:
            totals[sku] += Decimal(lot.quantity or 0)
    return totals


def reconcile_storage_records(dry_run: bool = True):
    """Compare inventory vs storage lots (by SKU) and optionally delete empty lots.

    Returns a dict containing lists of mismatches, missing_links, and lots_removed.
    """
    report = {
        "missing_links": [],  # inventory items without batch ID
        "mismatched_skus": [],  # {sku, inventory_qty, storage_qty}
        "lots_removed": [],  # storage lot IDs deleted due to <= 0 qty
    }

    storage_totals = aggregate_storage_by_sku()

    for item in InventoryItem.objects.all():
        if not item.batch_id:
            report["missing_links"].append({
                "sku": item.sku,
                "name": item.name,
            })
            continue
        storage_total = storage_totals.get(item.sku, Decimal("0"))
        item_qty = item.current_quantity or Decimal("0")
        # Allow small rounding differences
        if abs(storage_total - item_qty) > Decimal("0.01"):
            report["mismatched_skus"].append({
                "sku": item.sku,
                "name": item.name,
                "inventory_qty": item_qty,
                "storage_qty": storage_total,
            })

    zero_lots = ColdStorageInventory.objects.filter(quantity__lte=0)
    if dry_run:
        report["lots_removed"] = list(zero_lots.values_list("storage_id", flat=True))
    else:
        for lot in zero_lots:
            report["lots_removed"].append(lot.storage_id)
            lot.delete()

    return report

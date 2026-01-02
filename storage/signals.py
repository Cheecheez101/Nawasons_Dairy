"""Auto-sync InventoryItem whenever ColdStorageInventory changes."""
from decimal import Decimal

from django.db.models import Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from inventory.models import InventoryItem, InventoryTransaction

from .models import ColdStorageInventory


def _sync_inventory_for_sku(sku, latest_batch=None, reason="Storage auto-sync"):
    """Recalculate InventoryItem.current_quantity from all storage lots for a SKU."""
    if not sku:
        return

    # Sum all storage lots for this SKU (across all batches with the same SKU)
    storage_total = (
        ColdStorageInventory.objects
        .filter(production_batch__sku=sku)
        .aggregate(total=Sum("quantity"))
    )["total"] or Decimal("0")

    # Get earliest expiry among lots for this SKU
    earliest_expiry = (
        ColdStorageInventory.objects
        .filter(production_batch__sku=sku, expiry_date__isnull=False)
        .order_by("expiry_date")
        .values_list("expiry_date", flat=True)
        .first()
    )

    # Get the most recent batch_id for this SKU
    latest_batch_id = None
    if latest_batch:
        latest_batch_id = latest_batch.id
    else:
        latest_lot = (
            ColdStorageInventory.objects
            .filter(production_batch__sku=sku)
            .order_by("-last_restocked")
            .select_related("production_batch")
            .first()
        )
        if latest_lot and latest_lot.production_batch:
            latest_batch_id = latest_lot.production_batch.id
            latest_batch = latest_lot.production_batch

    today = timezone.now().date()

    try:
        item = InventoryItem.objects.get(sku=sku)
    except InventoryItem.DoesNotExist:
        # Auto-create if storage exists but inventory item doesn't
        if storage_total > 0 and latest_batch:
            item = InventoryItem.objects.create(
                name=latest_batch.get_product_type_display(),
                sku=sku,
                unit="UNIT",
                current_quantity=storage_total,
                product_category=latest_batch.product_type,
                is_processed=True,
                batch_id=latest_batch_id,
                expiry_date=earliest_expiry,
                last_restocked=today,
            )
            InventoryTransaction.objects.create(
                item=item,
                quantity=storage_total,
                reason=reason,
                batch_id=latest_batch_id,
            )
        return

    old_qty = Decimal(item.current_quantity or 0)
    delta = storage_total - old_qty

    # Update item
    item.current_quantity = storage_total
    if latest_batch_id and item.batch_id != latest_batch_id:
        item.batch_id = latest_batch_id
    if earliest_expiry:
        item.expiry_date = earliest_expiry
    item.last_restocked = today
    item.save(update_fields=["current_quantity", "batch_id", "expiry_date", "last_restocked"])

    # Log transaction if quantity changed
    if delta != 0:
        InventoryTransaction.objects.create(
            item=item,
            quantity=delta,
            reason=reason,
            batch_id=latest_batch_id,
        )


@receiver(post_save, sender=ColdStorageInventory)
def sync_inventory_on_storage_save(sender, instance, created, **kwargs):
    """Whenever a storage lot is created or updated, sync the linked inventory item."""
    batch = getattr(instance, "production_batch", None)
    sku = getattr(batch, "sku", None) if batch else None
    reason = "Storage lot created" if created else "Storage lot updated"
    _sync_inventory_for_sku(sku, latest_batch=batch, reason=reason)


@receiver(post_delete, sender=ColdStorageInventory)
def sync_inventory_on_storage_delete(sender, instance, **kwargs):
    """When a storage lot is deleted, recalculate inventory from remaining lots."""
    batch = getattr(instance, "production_batch", None)
    sku = getattr(batch, "sku", None) if batch else None
    _sync_inventory_for_sku(sku, latest_batch=batch, reason="Storage lot removed")

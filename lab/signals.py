from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import RawMilkTest, TankBatchTest, LabBatchApproval
from production.models import MilkYield
from inventory.models import InventoryItem


@receiver(post_save, sender=RawMilkTest)
def enforce_raw_approval(sender, instance, created, **kwargs):
    """
    After a raw milk test, update the MilkYield flag.
    Only approved yields can be stored in tanks or consumed later.
    """
    yield_obj = instance.milk_yield
    yield_obj.raw_test_approved = (instance.result == "approved")
    yield_obj.save(update_fields=["raw_test_approved"])


@receiver(post_save, sender=TankBatchTest)
def enforce_tank_approval(sender, instance, created, **kwargs):
    """
    After a tank batch test, update the MilkYield status.
    Only approved tanks can be consumed by ProductionBatch.
    """
    yield_obj = instance.milk_yield
    yield_obj.tank_test_latest_status = instance.result
    yield_obj.save(update_fields=["tank_test_latest_status"])


@receiver(post_save, sender=LabBatchApproval)
def move_approved_batch_to_inventory(sender, instance, created, **kwargs):
    """
    When Lab approves a finished product batch, create/update InventoryItem with expiry and quantity.
    """
    if instance.overall_result != "approved" or not instance.expiry_date:
        return

    batch = instance.production_batch
    qty = batch.quantity_produced

    item, created_item = InventoryItem.objects.get_or_create(
        sku=batch.sku,
        defaults={
            "name": batch.product_type,
            "unit": "UNIT",
            "current_quantity": qty,
            "expiry_date": instance.expiry_date,
            "batch_id": batch.id,
            "product_category": batch.product_type,
        },
    )

    if not created_item:
        # Update existing item
        item.current_quantity += qty
        item.expiry_date = instance.expiry_date
        item.batch_id = batch.id
        item.last_restocked = timezone.now().date()
        item.save()

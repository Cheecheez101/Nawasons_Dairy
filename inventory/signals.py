# inventory/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from lab.models import LabBatchApproval
from inventory.models import InventoryItem

@receiver(post_save, sender=LabBatchApproval)
def create_or_update_inventory(sender, instance, created, **kwargs):
    if instance.overall_result == "approved":
        batch = instance.production_batch
        item, _ = InventoryItem.objects.get_or_create(
            production_batch=batch,
            defaults={
                "name": str(batch),
                "current_quantity": batch.litres,
                "expiry_date": instance.expiry_date,
            }
        )
        # Update if already exists
        item.current_quantity = batch.litres
        item.expiry_date = instance.expiry_date
        item.save()

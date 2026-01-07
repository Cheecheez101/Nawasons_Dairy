from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from decimal import Decimal

from lab.models import MilkYield as LabMilkYield

class Cow(models.Model):
    HEALTH_STATUSES = [
        ("healthy", "Healthy"),
        ("monitor", "Monitor"),
        ("sick", "Needs Attention"),
    ]

    cow_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=60, blank=True)
    breed = models.CharField(max_length=50)
    date_of_birth = models.DateField()
    health_status = models.CharField(max_length=20, choices=HEALTH_STATUSES, default="healthy")
    stall_location = models.CharField(max_length=50, blank=True)
    daily_capacity_litres = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["cow_id"]

    def __str__(self):
        return self.cow_id

    @property
    def age_in_days(self):
        return (timezone.now().date() - self.date_of_birth).days

    def latest_yield(self):
        return self.yields.order_by('-recorded_at').first()


MilkYield = LabMilkYield


class ProductPrice(models.Model):
    inventory_item = models.OneToOneField(
        'inventory.InventoryItem',
        on_delete=models.PROTECT,
        related_name='product_price',
    )
    sku = models.CharField(max_length=30, unique=True)
    product_name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # Optional bulk price when customers buy full cartons
    bulk_price_per_carton = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='product_prices',
    )

    class Meta:
        ordering = ['product_name']
        permissions = [
            ('view_productpricechangelog', 'Can view product price change logs'),
        ]

    def __str__(self):
        return f"{self.product_name} ({self.sku})"

    def save(self, *args, **kwargs):
        if self.inventory_item_id:
            self.sku = self.inventory_item.sku
            self.product_name = self.inventory_item.name
        previous_price = None
        if self.pk:
            previous_price = ProductPrice.objects.only('price').get(pk=self.pk).price
        super().save(*args, **kwargs)
        if self.updated_by_id and (previous_price is None or previous_price != self.price):
            ProductPriceChangeLog.objects.create(
                product_price=self,
                old_price=previous_price,
                new_price=self.price,
                changed_by=self.updated_by,
            )

    @classmethod
    def current_for_inventory(cls, inventory_item):
        try:
            return cls.objects.get(inventory_item=inventory_item)
        except cls.DoesNotExist:
            return None


class ProductPriceChangeLog(models.Model):
    product_price = models.ForeignKey(
        ProductPrice,
        on_delete=models.CASCADE,
        related_name='change_logs',
    )
    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='product_price_change_logs',
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.product_price} changed at {self.changed_at:%Y-%m-%d %H:%M}"


class ProductionBatch(models.Model):
    class Status(models.TextChoices):
        PENDING_LAB = ("pending_lab", "Awaiting Lab")
        LAB_APPROVED = ("lab_approved", "Lab Approved")
        READY_FOR_STORE = ("ready_for_store", "Ready for Storage")

    PRODUCT_CHOICES = [
        ('atm', 'Fresh Milk ATM'),
        ('raw', 'Raw Milk (Bulk)'),
        ('esl', 'ESL Milk'),
        ('yogurt', 'Yogurt'),
        ('mala', 'Mala'),
        ('ghee', 'Ghee'),
    ]

    source_tank = models.CharField(max_length=40, choices=[(tank, tank) for tank in MilkYield.TANK_CAPACITY_LITRES.keys() if tank != 'Unassigned'])
    product_type = models.CharField(max_length=20, choices=PRODUCT_CHOICES)
    sku = models.CharField(max_length=30)  # e.g. MALA-CL-500
    quantity_produced = models.DecimalField(max_digits=10, decimal_places=2)
    liters_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    produced_at = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="production_batches")
    moved_to_lab = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_LAB)

    class Meta:
        ordering = ["-produced_at"]

    def __str__(self):
        return f"{self.product_type} batch {self.id} from {self.source_tank}"

    def consume_milk(self):
        """
        Deduct milk from the source tank when a production batch is created.
        Ensures only acceptable quality grades (standard/premium) are consumed.
        """
        yields_in_tank = MilkYield.objects.filter(
            storage_tank=self.source_tank,
            quality_grade__in=["premium", "standard"],
        ).order_by('recorded_at')

        liters_needed = self.liters_used or Decimal('0')
        if liters_needed <= 0:
            raise ValidationError("Liters used must be greater than zero before consuming milk")

        total_available = sum(y.yield_litres for y in yields_in_tank)
        if total_available < liters_needed:
            raise ValidationError("Not enough milk in tank for this production batch")

        # Deduct from yields, starting from oldest
        remaining = liters_needed
        for y in yields_in_tank:
            if remaining <= 0:
                break
            deduct = min(remaining, y.yield_litres)
            y.yield_litres -= deduct
            y.save(update_fields=["yield_litres"])
            remaining -= deduct

        self.moved_to_lab = True
        self.status = self.Status.PENDING_LAB


class StorageLocation(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    capacity = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ColdStorageInventory(models.Model):
    STATUS_CHOICES = [
        ("in_storage", "✅ In cold storage"),
        ("near_expiry", "⏳ Near expiry — prioritize dispatch"),
        ("expired", "❌ Expired — block dispatch"),
    ]

    storage_id = models.AutoField(primary_key=True)
    production_batch = models.OneToOneField(
        ProductionBatch,
        on_delete=models.CASCADE,
        related_name="production_storage_record",
    )
    product = models.CharField(max_length=100)
    expiry_date = models.DateField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    location = models.ForeignKey(StorageLocation, on_delete=models.PROTECT, related_name="inventory")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="in_storage")
    last_restocked = models.DateTimeField(auto_now_add=True)
    audit_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["expiry_date"]

    def __str__(self):
        return f"Storage #{self.storage_id} - {self.product}"

    def update_status(self):
        today = timezone.now().date()
        if self.expiry_date < today:
            self.status = "expired"
        elif (self.expiry_date - today).days <= 3:
            self.status = "near_expiry"
        else:
            self.status = "in_storage"
        self.save(update_fields=["status"])

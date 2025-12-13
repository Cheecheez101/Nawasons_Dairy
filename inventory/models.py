from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal


class InventoryItem(models.Model):
    UNIT_CHOICES = [
        ('L', 'Litres'),
        ('KG', 'Kilograms'),
        ('UNIT', 'Units'),
    ]
    PRODUCT_CATEGORIES = [
        ('raw', 'Raw Milk Storage'),
        ('atm', 'Fresh Milk ATM'),
        ('esl', 'ESL Milk'),
        ('yogurt', 'Yogurt'),
        ('mala', 'Mala'),
        ('ghee', 'Ghee'),
    ]

    name = models.CharField(max_length=120)
    sku = models.CharField(max_length=30, unique=True)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='L')
    current_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reorder_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reorder_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    last_restocked = models.DateField(null=True, blank=True)
    supplier_name = models.CharField(max_length=120, blank=True)
    default_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    product_category = models.CharField(max_length=20, choices=PRODUCT_CATEGORIES, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    flavor = models.CharField(max_length=100, blank=True)
    size_ml = models.PositiveIntegerField(null=True, blank=True)
    is_processed = models.BooleanField(default=False)

    # NEW FIELDS
    expiry_date = models.DateField(null=True, blank=True)   # issued by Lab
    batch_id = models.PositiveIntegerField(null=True, blank=True)  # link to MilkYield/LabBatchApproval

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def needs_reorder(self):
        """True if current stock is at or below threshold."""
        return Decimal(self.current_quantity) <= Decimal(self.reorder_threshold)

    @property
    def is_expired(self):
        """True if expiry_date is set and before today."""
        return bool(self.expiry_date and self.expiry_date < timezone.now().date())

    @property
    def is_near_expiry(self):
        """True if expiry_date is within 2 days."""
        return bool(self.expiry_date and (self.expiry_date - timezone.now().date()).days <= 2)

    @property
    def stock_percentage(self):
        """Percentage of stock relative to reorder threshold."""
        if self.reorder_threshold > 0:
            return round((self.current_quantity / self.reorder_threshold) * 100, 1)
        return 0

    def consume(self, amount):
        """Consume stock safely, preventing expired or insufficient stock usage."""
        if amount > self.current_quantity:
            raise ValidationError(f"Not enough stock for {self.name}")
        if self.is_expired:
            raise ValidationError(f"Cannot consume expired stock for {self.name}")
        self.current_quantity -= amount
        self.save(update_fields=['current_quantity'])


class InventoryTransaction(models.Model):
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='transactions')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=120)
    created_at = models.DateTimeField(default=timezone.now)

    # NEW FIELD
    batch_id = models.PositiveIntegerField(null=True, blank=True)  # track which batch this transaction relates to

    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('dispatch_product', 'Can dispatch finished products'),
        ]

    def __str__(self):
        return f"{self.item.name} - {self.quantity} ({self.reason})"

    def apply(self):
        """
        Apply transaction to inventory:
        - Prevent restocking expired batches
        - Allow both positive (restock) and negative (dispatch) quantities
        """
        if self.quantity > 0 and self.item.is_expired:
            raise ValidationError(f"Cannot restock expired batch for {self.item.name}")

        if self.quantity < 0 and abs(self.quantity) > self.item.current_quantity:
            raise ValidationError(f"Not enough stock to dispatch {self.item.name}")

        self.item.current_quantity += self.quantity
        self.item.last_restocked = timezone.now().date()
        self.item.save(update_fields=['current_quantity', 'last_restocked'])

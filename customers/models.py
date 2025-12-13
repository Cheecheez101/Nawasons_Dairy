from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models

# Create your models here.

class Customer(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    loyalty_points = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class CustomerInteraction(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='interactions')
    interaction_type = models.CharField(max_length=50)
    notes = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer.name} - {self.interaction_type}"

class LoyaltyLedger(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='loyalty_ledger')
    points_change = models.IntegerField()
    balance_after = models.IntegerField()
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer.name}: {self.points_change} pts"

class LoyaltyTier(models.Model):
    name = models.CharField(max_length=120)
    min_spend = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    max_spend = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    points_awarded = models.PositiveIntegerField()
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['min_spend']

    def __str__(self):
        upper = self.max_spend if self.max_spend is not None else '∞'
        return f"{self.name}: {self.min_spend} - {upper} => {self.points_awarded}pts"

    @classmethod
    def points_for_amount(cls, amount: Decimal) -> int:
        amount = Decimal(amount).quantize(Decimal('0.01'))
        tier = cls.objects.filter(
            min_spend__lte=amount,
        ).filter(
            models.Q(max_spend__gte=amount) | models.Q(max_spend__isnull=True)
        ).order_by('-min_spend').first()
        return tier.points_awarded if tier else 0

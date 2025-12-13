from django.core.management.base import BaseCommand
from inventory.models import InventoryItem

BASE_PRODUCTS = [
    {
        'name': 'Raw Milk Tank A',
        'sku': 'RM-A',
        'unit': 'L',
        'product_category': 'raw',
        'is_processed': False,
    },
    {
        'name': 'Fresh Milk ATM - Town',
        'sku': 'ATM-TOWN',
        'unit': 'L',
        'product_category': 'atm',
        'is_processed': True,
        'brand': 'Nawa Fresh',
        'size_ml': 500,
    },
    {
        'name': 'ESL Milk Vanilla 500ml',
        'sku': 'ESL-VAN-500',
        'unit': 'UNIT',
        'product_category': 'esl',
        'is_processed': True,
        'brand': 'Nawa ESL',
        'flavor': 'Vanilla',
        'size_ml': 500,
    },
    {
        'name': 'ESL Milk Strawberry 500ml',
        'sku': 'ESL-STR-500',
        'unit': 'UNIT',
        'product_category': 'esl',
        'is_processed': True,
        'brand': 'Nawa ESL',
        'flavor': 'Strawberry',
        'size_ml': 500,
    },
    {
        'name': 'Yogurt Plain 250ml',
        'sku': 'YOG-PL-250',
        'unit': 'UNIT',
        'product_category': 'yogurt',
        'is_processed': True,
        'brand': 'Nawa Yog',
        'flavor': 'Plain',
        'size_ml': 250,
    },
    {
        'name': 'Mala Classic 500ml',
        'sku': 'MALA-CL-500',
        'unit': 'UNIT',
        'product_category': 'mala',
        'is_processed': True,
        'brand': 'Nawa Mala',
        'size_ml': 500,
    },
    {
        'name': 'Ghee Premium 250ml',
        'sku': 'GHEE-PR-250',
        'unit': 'KG',
        'product_category': 'ghee',
        'is_processed': True,
        'brand': 'Nawa Ghee',
        'size_ml': 250,
    },
]

class Command(BaseCommand):
    help = 'Seed processed dairy products into inventory.'

    def handle(self, *args, **options):
        created = 0
        for product in BASE_PRODUCTS:
            obj, was_created = InventoryItem.objects.update_or_create(
                sku=product['sku'],
                defaults={
                    'name': product['name'],
                    'unit': product.get('unit', 'UNIT'),
                    'product_category': product.get('product_category'),
                    'brand': product.get('brand', ''),
                    'flavor': product.get('flavor', ''),
                    'size_ml': product.get('size_ml'),
                    'is_processed': product.get('is_processed', True),
                }
            )
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} products (existing updated)."))


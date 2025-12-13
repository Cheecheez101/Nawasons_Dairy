from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from inventory.models import InventoryItem

CONVERSION_RULES = {
    'atm': {'yield_per_litre': 1},
    'esl': {'yield_per_litre': 2},
    'yogurt': {'yield_per_litre': 3},
    'mala': {'yield_per_litre': 3},
    'ghee': {'yield_per_litre': 0.2},
}

class Command(BaseCommand):
    help = 'Convert raw milk tank volume into processed inventory.'

    def add_arguments(self, parser):
        parser.add_argument('--source-sku', required=True, help='SKU of raw tank (e.g., RM-A)')
        parser.add_argument('--category', required=True, choices=CONVERSION_RULES.keys())
        parser.add_argument('--litres', type=float, required=True)

    def handle(self, *args, **options):
        source_sku = options['source_sku']
        category = options['category']
        litres = options['litres']

        try:
            source = InventoryItem.objects.get(sku=source_sku)
        except InventoryItem.DoesNotExist:
            raise CommandError(f"Source SKU {source_sku} not found")

        processed_items = InventoryItem.objects.filter(product_category=category, is_processed=True)
        if not processed_items.exists():
            raise CommandError(f"No processed items defined for category {category}")

        rule = CONVERSION_RULES[category]
        yield_units = litres * rule['yield_per_litre']

        with transaction.atomic():
            source.consume(litres)
            per_item = yield_units / processed_items.count()
            for item in processed_items:
                item.current_quantity += per_item
                item.save(update_fields=['current_quantity'])

        self.stdout.write(self.style.SUCCESS(
            f"Converted {litres}L from {source_sku} into {yield_units} units across {processed_items.count()} SKUs"
        ))


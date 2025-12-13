from django.apps import AppConfig


class InventoryConfig(AppConfig):
    name = 'inventory'
# inventory/apps.py
def ready(self):
    import inventory.signals

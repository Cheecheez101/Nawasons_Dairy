from datetime import date, timedelta

DEFAULT_SHELF_LIFE_BY_PRODUCT = {
    # Map SKU or product categories to shelf life
    "MALA-CL-500": 14,
    "YOG-PL-250": 10,
    "ESL-VAN-500": 21,
    "ESL-STR-500": 21,
    "GHEE-PR-250": 180,
    "ATM-TOWN": 3,
}

def compute_expiry_for_sku(sku: str, start_date: date = None) -> date:
    start_date = start_date or date.today()
    days = DEFAULT_SHELF_LIFE_BY_PRODUCT.get(sku, 7)
    return start_date + timedelta(days=days)

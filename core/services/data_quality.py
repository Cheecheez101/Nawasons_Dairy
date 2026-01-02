from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, Set

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from core.models import DataQualityAlert
from inventory.models import InventoryItem
from sales.models import SalesTransaction
from storage.models import ColdStorageInventory, StorageLocation

LINE_TOTAL_EXPR = ExpressionWrapper(
    F("items__quantity") * F("items__price_per_unit"),
    output_field=DecimalField(max_digits=12, decimal_places=2),
)

StorageSnapshot = Dict[int, Dict[str, Any]]


def run_data_quality_checks() -> Iterable[DataQualityAlert]:
    """Run integrity checks and persist alert records."""

    storage_snapshot = _build_storage_snapshot()
    active_codes: Set[str] = set()
    active_codes.update(_check_negative_inventory(storage_snapshot))
    active_codes.update(_check_expired_inventory(storage_snapshot))
    active_codes.update(_check_sales_totals())
    active_codes.update(_check_storage_capacity())
    active_codes.update(_check_storage_expiry())

    _resolve_inactive_alerts(active_codes)
    return DataQualityAlert.objects.filter(resolved_at__isnull=True).order_by("-detected_at")


def _check_negative_inventory(storage_snapshot: StorageSnapshot) -> Set[str]:
    codes: Set[str] = set()
    for item in InventoryItem.objects.all():
        system_qty = item.current_quantity or Decimal("0")
        batch_entry = storage_snapshot.get(item.batch_id)
        storage_qty = batch_entry["quantity"] if batch_entry else None
        effective_qty = storage_qty if storage_qty is not None else system_qty

        if effective_qty < 0:
            code = f"inventory-negative-{item.pk}"
            message = f"{item.name} has negative stock ({system_qty})."
            if storage_qty is not None and storage_qty != system_qty:
                message += f" Storage register shows {storage_qty}."
            _upsert_alert(
                code,
                category="Inventory",
                message=message,
                severity="critical",
                model_label="inventory.InventoryItem",
                record_id=str(item.pk),
            )
            codes.add(code)
    return codes


def _check_expired_inventory(storage_snapshot: StorageSnapshot) -> Set[str]:
    codes: Set[str] = set()
    today = timezone.now().date()
    for item in InventoryItem.objects.all():
        batch_entry = storage_snapshot.get(item.batch_id)
        storage_qty = batch_entry["quantity"] if batch_entry else None
        storage_expiry = batch_entry["expiry"] if batch_entry else None
        system_qty = item.current_quantity or Decimal("0")
        effective_qty = storage_qty if storage_qty is not None else system_qty
        expiry_reference = storage_expiry or item.expiry_date

        if expiry_reference and expiry_reference < today and effective_qty > 0:
            code = f"inventory-expired-{item.pk}"
            message = (
                f"{item.name} stock is expired since {expiry_reference}."
            )
            if storage_expiry and storage_expiry != item.expiry_date:
                message += f" Storage batch shows {storage_expiry}."
            _upsert_alert(
                code,
                category="Inventory",
                message=message,
                severity="warning",
                model_label="inventory.InventoryItem",
                record_id=str(item.pk),
            )
            codes.add(code)
    return codes


def _check_sales_totals() -> Set[str]:
    codes: Set[str] = set()
    transactions = (
        SalesTransaction.objects
        .annotate(computed_total=Sum(LINE_TOTAL_EXPR))
        .only("id", "transaction_id", "total_amount")
    )
    for tx in transactions:
        computed = tx.computed_total or Decimal("0")
        delta = abs((tx.total_amount or Decimal("0")) - computed)
        if delta.quantize(Decimal("0.01")) > Decimal("1.00"):
            code = f"sales-mismatch-{tx.pk}"
            _upsert_alert(
                code,
                category="Sales",
                message=f"Transaction {tx.transaction_id} total differs by {delta:.2f}.",
                severity="critical",
                model_label="sales.SalesTransaction",
                record_id=str(tx.pk),
            )
            codes.add(code)
    return codes


def _check_storage_capacity() -> Set[str]:
    codes: Set[str] = set()
    locations = StorageLocation.objects.annotate(on_hand=Sum('inventory__quantity'))
    for location in locations:
        capacity = location.capacity or Decimal('0')
        on_hand = location.on_hand or Decimal('0')
        if capacity and on_hand > capacity:
            code = f"storage-capacity-{location.pk}"
            _upsert_alert(
                code,
                category="Storage",
                message=(
                    f"{location.name} holds {on_hand} units which exceeds its capacity of {capacity}."
                ),
                severity="critical",
                model_label="storage.StorageLocation",
                record_id=str(location.pk),
            )
            codes.add(code)
    return codes


def _check_storage_expiry() -> Set[str]:
    codes: Set[str] = set()
    today = timezone.now().date()
    near_cutoff = today + timedelta(days=3)

    expired_lots = ColdStorageInventory.objects.select_related('location').filter(expiry_date__lt=today)
    for lot in expired_lots:
        code = f"storage-expired-{lot.pk}"
        _upsert_alert(
            code,
            category="Storage",
            message=(
                f"{lot.product} in {lot.location.name} expired on {lot.expiry_date}."
            ),
            severity="critical",
            model_label="storage.ColdStorageInventory",
            record_id=str(lot.pk),
        )
        codes.add(code)

    near_expiry_lots = (
        ColdStorageInventory.objects
        .select_related('location')
        .filter(expiry_date__gte=today, expiry_date__lte=near_cutoff)
    )
    for lot in near_expiry_lots:
        code = f"storage-near-expiry-{lot.pk}"
        _upsert_alert(
            code,
            category="Storage",
            message=(
                f"{lot.product} in {lot.location.name} expires on {lot.expiry_date}."
            ),
            severity="warning",
            model_label="storage.ColdStorageInventory",
            record_id=str(lot.pk),
        )
        codes.add(code)
    return codes


def _upsert_alert(
    code: str,
    *,
    category: str,
    message: str,
    severity: str,
    model_label: str,
    record_id: str,
) -> DataQualityAlert:
    defaults = {
        "category": category,
        "message": message,
        "severity": severity,
        "model_label": model_label,
        "record_id": record_id,
    }
    alert, created = DataQualityAlert.objects.get_or_create(code=code, defaults=defaults)
    if not created:
        updated_fields = []
        for field, value in defaults.items():
            if getattr(alert, field) != value:
                setattr(alert, field, value)
                updated_fields.append(field)
        if alert.resolved_at is not None:
            alert.resolved_at = None
            alert.auto_resolved = False
            updated_fields.extend(["resolved_at", "auto_resolved"])
        if updated_fields:
            alert.save(update_fields=list(set(updated_fields)))
    return alert


def _resolve_inactive_alerts(active_codes: Set[str]) -> None:
    if not active_codes:
        inactive_qs = DataQualityAlert.objects.filter(resolved_at__isnull=True)
    else:
        inactive_qs = DataQualityAlert.objects.filter(resolved_at__isnull=True).exclude(code__in=active_codes)
    if inactive_qs.exists():
        inactive_qs.update(resolved_at=timezone.now(), auto_resolved=True)


def _build_storage_snapshot() -> StorageSnapshot:
    snapshot: StorageSnapshot = {}
    lots = ColdStorageInventory.objects.values("production_batch_id", "quantity", "expiry_date")
    for lot in lots:
        batch_id = lot["production_batch_id"]
        if not batch_id:
            continue
        entry = snapshot.setdefault(batch_id, {"quantity": Decimal("0"), "expiry": None})
        entry["quantity"] += Decimal(lot["quantity"]) if lot["quantity"] is not None else Decimal("0")
        expiry = lot["expiry_date"]
        if expiry and (entry["expiry"] is None or expiry < entry["expiry"]):
            entry["expiry"] = expiry
    return snapshot

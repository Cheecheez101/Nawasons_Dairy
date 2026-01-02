from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import F, Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views import View

from lab.models import LabBatchApproval
from production.models import MilkYield
from storage.models import ColdStorageInventory

from .forms import InventoryItemForm
from .models import InventoryItem


class InventoryDashboardView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "inventory.view_inventoryitem"

    def get(self, request):
        # All inventory items
        items = list(InventoryItem.objects.all())

        # Items needing reorder (DB-level filter using fields)
        low_stock_items = list(
            InventoryItem.objects.filter(
                current_quantity__lte=F("reorder_threshold")
            )
        )

        # Processed items
        processed_items = list(InventoryItem.objects.filter(is_processed=True))

        # Map each batch-backed item to its cold-storage quantity
        batch_ids = {item.batch_id for item in items if item.batch_id}
        storage_quantities = {}
        if batch_ids:
            storage_totals = (
                ColdStorageInventory.objects
                .filter(production_batch_id__in=batch_ids)
                .values("production_batch_id")
                .annotate(total_quantity=Sum("quantity"))
            )
            storage_quantities = {
                entry["production_batch_id"]: entry["total_quantity"]
                for entry in storage_totals
            }

        def apply_storage_overlay(collection):
            for entry in collection:
                storage_qty = storage_quantities.get(entry.batch_id)
                entry.system_quantity = entry.current_quantity
                entry.storage_quantity = storage_qty
                entry.display_quantity = (
                    storage_qty if storage_qty is not None else entry.current_quantity
                )
                entry.quantity_source = "storage" if storage_qty is not None else "inventory"
                entry.system_is_negative = entry.current_quantity < 0
                entry.has_quantity_mismatch = (
                    storage_qty is not None and storage_qty != entry.current_quantity
                )

        apply_storage_overlay(items)
        apply_storage_overlay(low_stock_items)
        apply_storage_overlay(processed_items)

        # Tank totals (litres per tank)
        tank_totals = (
            MilkYield.objects
            .values("storage_tank")
            .annotate(total_litres=Sum("yield_litres"))
        )
        tank_summary = {entry["storage_tank"]: entry["total_litres"] for entry in tank_totals}

        # Build tank rows with capacity and percentage
        tank_rows = []
        for tank, capacity in MilkYield.TANK_CAPACITY_LITRES.items():
            volume = tank_summary.get(tank, 0) or 0
            percent = (float(volume) / float(capacity) * 100) if capacity else 0
            tank_rows.append({
                "name": tank,
                "volume": volume,
                "capacity": capacity,
                "percent": round(percent, 1),
            })

        # Lab approvals
        approvals = LabBatchApproval.objects.select_related("production_batch")

        # Cold storage insights
        today = timezone.now().date()
        alert_cutoff = today + timedelta(days=7)
        storage_qs = ColdStorageInventory.objects.select_related("location", "production_batch")

        expiring_inventory = []
        for lot in storage_qs.filter(expiry_date__lte=alert_cutoff).order_by("expiry_date"):
            days_left = (lot.expiry_date - today).days
            expiring_inventory.append({
                "storage_id": lot.storage_id,
                "product": lot.product,
                "production_batch": lot.production_batch,
                "expiry_date": lot.expiry_date,
                "days_left": days_left,
                "quantity": lot.quantity,
                "unit": "kg",
                "location": lot.location.name if lot.location else "—",
                "status": lot.status,
            })

        storage_locations = []
        location_totals = (
            storage_qs
            .values("location__name", "location__location_type", "location__capacity")
            .annotate(on_hand=Sum("quantity"))
            .order_by("location__name")
        )
        for entry in location_totals:
            capacity = float(entry["location__capacity"] or 0)
            on_hand = float(entry["on_hand"] or 0)
            percent = round((on_hand / capacity) * 100, 1) if capacity else 0
            storage_locations.append({
                "name": entry["location__name"],
                "type": entry["location__location_type"],
                "type_label": (entry["location__location_type"] or "").replace("_", " ").title(),
                "capacity": entry["location__capacity"],
                "on_hand": entry["on_hand"],
                "percent": percent,
            })


        # Extra summary metrics
        total_items = len(items)
        total_processed = len(processed_items)
        total_litres = sum(row["volume"] for row in tank_rows)

        return render(request, "inventory/dashboard.html", {
            "items": items,
            "low_stock_items": low_stock_items,
            "processed_items": processed_items,
            "tank_rows": tank_rows,
            "approvals": approvals,
            "storage_locations": storage_locations,
            "expiring_inventory": expiring_inventory,
            "total_items": total_items,
            "total_processed": total_processed,
            "total_litres": total_litres,
        })


class InventoryItemCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "inventory.add_inventoryitem"

    def get(self, request):
        form = InventoryItemForm()
        return render(request, "inventory/item_form.html", {
            "form": form,
            "title": "Add Inventory Item",
            "submit_label": "Create Item",
        })

    def post(self, request):
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            item = form.save()
            messages.success(request, f"{item.name} added to inventory.")
            return redirect("inventory:dashboard")
        return render(request, "inventory/item_form.html", {
            "form": form,
            "title": "Add Inventory Item",
            "submit_label": "Create Item",
        })


class InventoryItemUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "inventory.change_inventoryitem"

    def get(self, request, pk):
        item = get_object_or_404(InventoryItem, pk=pk)
        form = InventoryItemForm(instance=item)
        return render(request, "inventory/item_form.html", {
            "form": form,
            "item": item,
            "title": "Edit Inventory Item",
            "submit_label": "Save Changes",
        })

    def post(self, request, pk):
        item = get_object_or_404(InventoryItem, pk=pk)
        form = InventoryItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f"{item.name} updated successfully.")
            return redirect("inventory:dashboard")
        return render(request, "inventory/item_form.html", {
            "form": form,
            "item": item,
            "title": "Edit Inventory Item",
            "submit_label": "Save Changes",
        })


class InventoryItemDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "inventory.delete_inventoryitem"

    def get(self, request, pk):
        item = get_object_or_404(InventoryItem, pk=pk)
        return render(request, "inventory/item_confirm_delete.html", {"item": item})

    def post(self, request, pk):
        item = get_object_or_404(InventoryItem, pk=pk)
        name = item.name
        item.delete()
        messages.success(request, f"{name} removed from inventory.")
        return redirect("inventory:dashboard")

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import F, Q, Sum, ExpressionWrapper, DecimalField
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.views import View

from lab.models import LabBatchApproval
from production.models import MilkYield
from production.models import ProductPrice
from storage.models import ColdStorageInventory

from .forms import InventoryItemForm
from .models import InventoryItem


class InventoryDashboardView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "inventory.view_inventoryitem"

    def get(self, request):
        # All inventory items
        items_qs = InventoryItem.objects.all()
        
        # Apply filters for items table
        item_search = request.GET.get('item_q', '').strip()
        if item_search:
            items_qs = items_qs.filter(
                Q(name__icontains=item_search) | Q(sku__icontains=item_search)
            )
        
        category = request.GET.get('category', '').strip()
        if category:
            items_qs = items_qs.filter(product_category=category)
        
        stock_status = request.GET.get('stock_status', '').strip()
        if stock_status == 'low':
            items_qs = items_qs.filter(current_quantity__lte=F('reorder_threshold'), current_quantity__gt=0)
        elif stock_status == 'out':
            items_qs = items_qs.filter(current_quantity__lte=0)
        elif stock_status == 'in_stock':
            items_qs = items_qs.filter(current_quantity__gt=F('reorder_threshold'))
        
        items = list(items_qs)

        # Attach packaging and bulk pricing metadata to each inventory item for display
        for item in items:
            try:
                pkg = item.packagings.order_by('-pack_size_ml').first()
                item.pack_size_ml = getattr(pkg, 'pack_size_ml', None)
                item.packets_per_carton = getattr(pkg, 'packets_per_carton', None)
            except Exception:
                item.pack_size_ml = None
                item.packets_per_carton = None

            try:
                pp = ProductPrice.current_for_inventory(item)
                item.bulk_price_per_carton = getattr(pp, 'bulk_price_per_carton', None)
            except Exception:
                item.bulk_price_per_carton = None

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
            total_units_expr = ExpressionWrapper(
                F('cartons') * F('packaging__packets_per_carton') + F('loose_units'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
            storage_totals = (
                ColdStorageInventory.objects
                .filter(production_batch_id__in=batch_ids)
                .values("production_batch_id")
                .annotate(total_quantity=Sum(total_units_expr))
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
            # Use total units (cartons*packets + loose_units)
            try:
                total = lot.total_units()
            except Exception:
                total = getattr(lot, 'loose_units', 0) or 0
            expiring_inventory.append({
                "storage_id": lot.storage_id,
                "product": str(lot.packaging) if lot.packaging else lot.production_batch.get_product_type_display(),
                "production_batch": lot.production_batch,
                "expiry_date": lot.expiry_date,
                "days_left": days_left,
                "quantity": total,
                "unit": "units",
                "location": lot.location.name if lot.location else "—",
                "status": lot.status,
            })

        storage_locations = []
        total_units_expr = ExpressionWrapper(
            F('cartons') * F('packaging__packets_per_carton') + F('loose_units'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        location_totals = (
            storage_qs
            .values("location__name", "location__location_type", "location__capacity")
            .annotate(on_hand=Sum(total_units_expr))
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
        try:
            item.delete()
            messages.success(request, f"{name} removed from inventory.")
        except ProtectedError as exc:
            # exc.protected_objects may not be available on all Django versions,
            # but exc.args[1] typically contains the set of blocking objects.
            blocked = set()
            if hasattr(exc, 'protected_objects'):
                blocked = set(exc.protected_objects)
            elif len(exc.args) > 1 and exc.args[1]:
                try:
                    blocked = set(exc.args[1])
                except Exception:
                    blocked = set()

            # Build a short human-readable list of blocking references
            blocked_list = []
            for obj in blocked:
                try:
                    blocked_list.append(str(obj))
                except Exception:
                    blocked_list.append(repr(obj))

            if blocked_list:
                messages.error(
                    request,
                    "Cannot delete this inventory item because it is referenced by other records: "
                    + ", ".join(blocked_list)
                )
            else:
                messages.error(request, "Cannot delete this inventory item because related records protect it.")
        return redirect("inventory:dashboard")

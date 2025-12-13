from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Sum, F
from .models import InventoryItem
from production.models import MilkYield
from lab.models import LabBatchApproval


class InventoryDashboardView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "inventory.view_inventoryitem"

    def get(self, request):
        # All inventory items
        items = InventoryItem.objects.all()

        # Items needing reorder (DB-level filter using fields)
        low_stock_items = InventoryItem.objects.filter(
            current_quantity__lte=F("reorder_threshold")
        )

        # Processed items
        processed_items = InventoryItem.objects.filter(is_processed=True)

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


        # Extra summary metrics
        total_items = items.count()
        total_processed = processed_items.count()
        total_litres = sum(row["volume"] for row in tank_rows)

        return render(request, "inventory/dashboard.html", {
            "items": items,
            "low_stock_items": low_stock_items,
            "processed_items": processed_items,
            "tank_rows": tank_rows,
            "approvals": approvals,
            "total_items": total_items,
            "total_processed": total_processed,
            "total_litres": total_litres,
        })

from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views import View
from production.models import MilkYield
from inventory.models import InventoryItem
from sales.models import SalesTransaction
from django.db.models import Sum
from django.utils import timezone

class ReportsDashboardView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'reports.view_report'

    def get(self, request):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        sales_queryset = SalesTransaction.objects.all()
        production_queryset = MilkYield.objects.all()
        if start_date:
            sales_queryset = sales_queryset.filter(created_at__date__gte=start_date)
            production_queryset = production_queryset.filter(recorded_at__gte=start_date)
        if end_date:
            sales_queryset = sales_queryset.filter(created_at__date__lte=end_date)
            production_queryset = production_queryset.filter(recorded_at__lte=end_date)
        production_stats = production_queryset.aggregate(total=Sum('total_yield'))
        inventory_stats = InventoryItem.objects.aggregate(total_stock=Sum('current_quantity'))
        sales_stats = sales_queryset.aggregate(total_sales=Sum('total_amount'))
        context = {
            'production_total': production_stats['total'] or 0,
            'inventory_total': inventory_stats['total_stock'] or 0,
            'sales_total': sales_stats['total_sales'] or 0,
            'start_date': start_date,
            'end_date': end_date,
        }
        return render(request, 'reports/dashboard.html', context)

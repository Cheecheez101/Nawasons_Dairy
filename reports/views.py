import io
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from customers.models import CustomerInteraction
from inventory.models import InventoryItem, InventoryTransaction
from production.models import MilkYield, ProductPriceChangeLog, ProductionBatch
from storage.models import ColdStorageInventory
from sales.models import SalesItem, SalesTransaction
from suppliers.models import SupplierOrder


class ReportsDashboardView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'reports.view_reports_dashboard'
    MODULE_TITLES = {
        'production': 'Production Intelligence',
        'inventory': 'Inventory Assurance',
        'sales': 'Commercial Pulse',
        'relationship': 'Relationship Analytics',
        'management': 'Leadership Cockpit',
    }
    MODULE_ALIASES = {
        'customers': 'relationship',
        'suppliers': 'relationship',
    }
    REPORT_LABELS = {
        'production': {
            'daily': 'Daily Milk Yield',
            'batch': 'Batch Production',
            'quality': 'Quality Control',
            'trends': 'Trend Analysis',
            'cow_yield': 'Cow Yield Leaders',
        },
        'inventory': {
            'stock': 'Stock Levels',
            'reorder': 'Reorder Alerts',
            'wastage': 'Wastage Summary',
            'delivery': 'Supplier Delivery',
            'storage': 'Storage Utilization',
            'storage_alerts': 'Storage Alerts',
        },
        'sales': {
            'daily': 'Daily Sales',
            'product': 'Product Performance',
            'customers': 'Customer Sales',
            'financials': 'Revenue vs Expenses',
            'cash': 'Cash Reconciliation',
        },
        'relationship': {
            'purchase_history': 'Customer Purchase History',
            'promotions': 'Promotions Effectiveness',
            'suppliers': 'Supplier Performance',
        },
        'management': {
            'efficiency': 'Efficiency',
            'productivity': 'Staff Productivity',
            'usage': 'System Usage',
            'forecasting': 'Forecasting',
        },
    }
    MODULE_FORM_PREFERENCES = {
        'relationship': 'customers',
    }
    REPORT_ALIAS_MAP = {
        'milk_yield': ('production', 'daily'),
        'batch_production': ('production', 'batch'),
        'quality_control': ('production', 'quality'),
        'production_trends': ('production', 'trends'),
        'stock_levels': ('inventory', 'stock'),
        'reorder_alerts': ('inventory', 'reorder'),
        'wastage': ('inventory', 'wastage'),
        'supplier_delivery': ('inventory', 'delivery'),
        'daily_sales': ('sales', 'daily'),
        'product_performance': ('sales', 'product'),
        'customer_sales': ('sales', 'customers'),
        'profitability': ('sales', 'financials'),
        'cash_recon': ('sales', 'cash'),
        'customer_history': ('relationship', 'purchase_history'),
        'promotions': ('relationship', 'promotions'),
        'supplier_performance': ('relationship', 'suppliers'),
        'efficiency': ('management', 'efficiency'),
        'productivity': ('management', 'productivity'),
        'system_usage': ('management', 'usage'),
        'forecasting': ('management', 'forecasting'),
        'cow_yield': ('production', 'cow_yield'),
    }

    def has_permission(self):
        if super().has_permission():
            return True
        return self.request.user.has_perm('reports.view_report')

    def get(self, request):
        start_raw = request.GET.get('start_date')
        end_raw = request.GET.get('end_date')
        module_param = request.GET.get('module', '')
        active_module = self._normalize_module(module_param)
        report_param = request.GET.get('report')
        report_module, normalized_report_key, report_slug = self._resolve_report_target(report_param)
        if report_module and not active_module:
            active_module = report_module

        start_date = self._parse_date(start_raw)
        end_date = self._parse_date(end_raw)

        milk_queryset = self._filter_queryset(MilkYield.objects.all(), 'recorded_at', start_date, end_date)
        sales_queryset = self._filter_queryset(SalesTransaction.objects.all(), 'created_at', start_date, end_date)
        batch_queryset = self._filter_queryset(ProductionBatch.objects.all(), 'produced_at', start_date, end_date)
        inventory_transactions = self._filter_queryset(InventoryTransaction.objects.all(), 'created_at', start_date, end_date)
        supplier_orders = self._filter_queryset(SupplierOrder.objects.all(), 'order_date', start_date, end_date, uses_date_lookup=False)
        price_changes = self._filter_queryset(ProductPriceChangeLog.objects.all(), 'changed_at', start_date, end_date)
        customer_interactions = self._filter_queryset(CustomerInteraction.objects.all(), 'created_at', start_date, end_date)
        sales_items = SalesItem.objects.filter(transaction__in=sales_queryset)
        storage_lots = self._filter_queryset(
            ColdStorageInventory.objects.select_related('location', 'production_batch'),
            'expiry_date',
            start_date,
            end_date,
            uses_date_lookup=False,
        )

        production_reports = self._build_production_reports(milk_queryset, batch_queryset)
        inventory_reports = self._build_inventory_reports(
            InventoryItem.objects.all(),
            inventory_transactions,
            supplier_orders,
            storage_lots,
        )
        sales_reports = self._build_sales_reports(sales_queryset, sales_items)
        relationship_reports = self._build_relationship_reports(sales_queryset, sales_items, supplier_orders, price_changes)
        management_reports = self._build_management_reports(
            milk_queryset,
            batch_queryset,
            sales_queryset,
            inventory_transactions,
            customer_interactions,
            supplier_orders,
        )

        export_format = request.GET.get('format')
        raw_report_key = (request.GET.get('report') or '').strip().lower()
        effective_report_key = normalized_report_key or raw_report_key or None

        context = {
            'production_reports': production_reports,
            'inventory_reports': inventory_reports,
            'sales_reports': sales_reports,
            'relationship_reports': relationship_reports,
            'management_reports': management_reports,
            'production_total': self._decimal(milk_queryset.aggregate(total=Sum('total_yield'))['total']),
            'inventory_total': self._decimal(InventoryItem.objects.aggregate(total_stock=Sum('current_quantity'))['total_stock']),
            'sales_total': self._decimal(sales_queryset.aggregate(total_sales=Sum('total_amount'))['total_sales']),
            'start_date': start_raw or (start_date.isoformat() if start_date else ''),
            'end_date': end_raw or (end_date.isoformat() if end_date else ''),
            'module': module_param,
            'active_module': active_module,
            'today': timezone.now().date(),
        }
        if export_format in {'pdf', 'excel'}:
            payload = self._collect_export_payload(
                active_module,
                effective_report_key,
                report_slug,
                production_reports,
                inventory_reports,
                sales_reports,
                relationship_reports,
                management_reports,
            )
            if export_format == 'excel':
                return self._export_excel(payload, start_date, end_date)
            return self._export_pdf(payload, start_date, end_date)
        return render(request, 'reports/dashboard.html', context)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _parse_date(self, value):
        if not value:
            return None
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return None

    def _filter_queryset(self, queryset, field_name, start, end, uses_date_lookup=True):
        if start:
            lookup = f"{field_name}__date__gte" if uses_date_lookup else f"{field_name}__gte"
            queryset = queryset.filter(**{lookup: start})
        if end:
            lookup = f"{field_name}__date__lte" if uses_date_lookup else f"{field_name}__lte"
            queryset = queryset.filter(**{lookup: end})
        return queryset

    def _decimal(self, value):
        if value is None:
            return Decimal('0')
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _format_number(self, value, suffix=''):
        val = self._decimal(value)
        if val == 0:
            formatted = '0'
        elif val == val.to_integral():
            formatted = f"{val.to_integral():,}"
        else:
            formatted = f"{val:,.2f}"
        return f"{formatted}{suffix}"

    def _format_currency(self, value):
        return f"KES {self._format_number(value)}"

    def _percent_of(self, part, whole):
        whole_val = self._decimal(whole)
        if whole_val == 0:
            return '0%'
        pct = (self._decimal(part) / whole_val) * Decimal('100')
        return f"{pct.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"

    def _percent_difference(self, actual, target):
        target_val = self._decimal(target)
        if target_val == 0:
            return '0%'
        diff = ((self._decimal(actual) - target_val) / target_val) * Decimal('100')
        sign = '+' if diff >= 0 else ''
        return f"{sign}{diff.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"

    def _status_from_ratio(self, ratio):
        ratio_val = self._decimal(ratio)
        if ratio_val >= Decimal('1.05'):
            return 'good', 'Above Target'
        if ratio_val >= Decimal('0.9'):
            return 'warning', 'Slight Dip'
        return 'critical', 'Below Target'

    def _banding_status(self, value, warning_level, good_level):
        number = self._decimal(value)
        if number >= self._decimal(good_level):
            return 'good', 'Strong'
        if number >= self._decimal(warning_level):
            return 'warning', 'Monitor'
        return 'critical', 'Needs Attention'

    def _spark_value(self, actual, target):
        target_val = self._decimal(target)
        if target_val == 0:
            return 0
        pct = (self._decimal(actual) / target_val) * Decimal('100')
        pct = max(Decimal('0'), min(Decimal('150'), pct))
        return int(pct)

    # ------------------------------------------------------------------
    # builders
    # ------------------------------------------------------------------
    def _build_production_reports(self, milk_queryset, batch_queryset):
        daily_rows = []
        tank_totals = (
            milk_queryset
            .values('storage_tank')
            .annotate(liters=Sum('yield_litres'))
            .order_by('storage_tank')
        )
        for row in tank_totals:
            tank = row['storage_tank'] or 'Unassigned'
            liters = self._decimal(row['liters'])
            target = MilkYield.TANK_CAPACITY_LITRES.get(tank, Decimal('500'))
            ratio = (liters / target) if target else Decimal('0')
            status, status_label = self._status_from_ratio(ratio)
            daily_rows.append({
                'tank': tank,
                'liters': self._format_number(liters, ' L'),
                'target': self._format_number(target, ' L'),
                'variance': self._percent_difference(liters, target),
                'status': status,
                'status_label': status_label,
            })

        batch_rows = []
        batch_totals = (
            batch_queryset
            .values('sku', 'product_type')
            .annotate(liters=Sum('liters_used'), units=Sum('quantity_produced'))
            .order_by('-units')[:10]
        )
        for row in batch_totals:
            liters = self._decimal(row['liters'])
            units = self._decimal(row['units'])
            ratio = (units / liters) if liters else Decimal('0')
            status, status_label = self._status_from_ratio(ratio)
            batch_rows.append({
                'sku': row['sku'] or row['product_type'],
                'liters': self._format_number(liters, ' L'),
                'units': self._format_number(units),
                'yield': self._percent_of(units, liters),
                'status': status,
                'status_label': status_label,
            })

        quality_rows = []
        quality_qs = (
            milk_queryset
            .filter(Q(quality_grade='low') | Q(quality_score__lt=80))
            .select_related('cow')
            .order_by('-recorded_at')[:6]
        )
        for entry in quality_qs:
            is_low_quality = entry.quality_grade == 'low' or (entry.quality_score or 0) < 80
            status = 'critical' if is_low_quality else 'warning'
            label = 'Hold' if status == 'critical' else 'Review'
            quality_rows.append({
                'batch': entry.storage_tank,
                'issue': entry.quality_notes or entry.get_quality_grade_display(),
                'volume': self._format_number(entry.yield_litres, ' L'),
                'action': 'Hold for retest' if is_low_quality else 'Blend or upgrade',
                'status': status,
                'status_label': label,
            })

        trends = []
        trend_data = (
            milk_queryset
            .annotate(period=TruncMonth('recorded_at'))
            .values('period')
            .annotate(volume=Sum('yield_litres'))
            .order_by('-period')[:6]
        )
        default_target = Decimal('2000')
        for row in trend_data:
            volume = self._decimal(row['volume'])
            target = default_target
            trends.append({
                'period': row['period'].strftime('%b %Y') if row['period'] else 'Current',
                'volume': self._format_number(volume, ' L'),
                'target': self._format_number(target, ' L'),
                'variance': self._percent_difference(volume, target),
                'trend': self._spark_value(volume, target),
                'trend_label': '▲ vs target' if volume >= target else '▼ vs target',
            })

        cow_rows = []
        cow_stats = (
            milk_queryset
            .values(
                'cow__cow_id',
                'cow__name',
                'cow__breed',
                'cow__health_status',
                'cow__daily_capacity_litres',
            )
            .annotate(total=Sum('yield_litres'))
            .order_by('-total')[:8]
        )
        health_labels = {
            'healthy': 'Healthy',
            'monitor': 'Monitor',
            'sick': 'Needs Attention',
        }
        for row in cow_stats:
            total = self._decimal(row['total'])
            declared_capacity = self._decimal(row['cow__daily_capacity_litres'] or Decimal('0'))
            baseline_capacity = declared_capacity if declared_capacity > 0 else Decimal('25')
            warning_level = baseline_capacity * Decimal('0.7')
            good_level = baseline_capacity * Decimal('0.95')
            status, performance_label = self._banding_status(total, warning_level, good_level)
            health_state = (row['cow__health_status'] or 'monitor').lower()
            health_label = health_labels.get(health_state, 'Monitor')
            cow_rows.append({
                'cow': row['cow__name'] or row['cow__cow_id'],
                'breed': row['cow__breed'] or 'Mixed',
                'yield': self._format_number(total, ' L'),
                'target': self._format_number(declared_capacity or baseline_capacity, ' L'),
                'status': status,
                'status_label': f"{performance_label} · {health_label}",
            })

        return {
            'daily': daily_rows,
            'batch': batch_rows,
            'quality': quality_rows,
            'trends': trends,
            'cow_yield': cow_rows,
        }

    def _build_inventory_reports(self, items_queryset, transactions_queryset, supplier_orders, storage_queryset):
        stock_rows = []
        reorder_rows = []
        for item in items_queryset.order_by('name')[:20]:
            coverage = self._coverage_label(item)
            status, status_label = self._inventory_status(item)
            stock_rows.append({
                'item': item.name,
                'qty': self._format_number(item.current_quantity),
                'unit': item.unit,
                'coverage': coverage,
                'status': status,
                'status_label': status_label,
            })
            if item.needs_reorder:
                status = 'critical' if item.current_quantity <= 0 else 'warning'
                reorder_rows.append({
                    'item': item.name,
                    'current': self._format_number(item.current_quantity),
                    'threshold': self._format_number(item.reorder_threshold),
                    'reorder': self._format_number(item.reorder_quantity or item.reorder_threshold),
                    'status': status,
                    'status_label': 'Out of stock' if status == 'critical' else 'Reorder soon',
                })

        wastage_rows = []
        wastage_qs = transactions_queryset.filter(
            Q(reason__icontains='waste') |
            Q(reason__icontains='expire') |
            Q(reason__icontains='damage')
        ).select_related('item').order_by('-created_at')[:6]
        for txn in wastage_qs:
            qty = abs(self._decimal(txn.quantity))
            value = qty * self._decimal(txn.item.default_price)
            wastage_rows.append({
                'item': txn.item.name,
                'quantity': self._format_number(qty, f" {txn.item.unit}"),
                'cause': txn.reason,
                'value': self._format_currency(value),
                'status': 'critical',
                'status_label': 'Investigate',
            })

        delivery_rows = []
        for order in supplier_orders.select_related('supplier', 'inventory_item').order_by('-order_date')[:8]:
            status = 'good' if order.status == 'delivered' else 'warning'
            shortage_value = self._decimal(order.quantity) - self._decimal(order.inventory_item.current_quantity)
            shortage_value = shortage_value if shortage_value > 0 else Decimal('0')
            delivery_rows.append({
                'supplier': order.supplier.name,
                'item': order.inventory_item.name,
                'on_time': 'Yes' if order.status == 'delivered' else 'Pending',
                'shortage': self._format_number(shortage_value),
                'status': status,
                'status_label': 'On Track' if status == 'good' else 'Follow up',
            })

        storage_rows = []
        storage_alerts = []
        if storage_queryset is not None:
            location_totals = (
                storage_queryset
                .values('location__name', 'location__capacity', 'location__location_type')
                .annotate(current=Sum('quantity'))
                .order_by('location__name')
            )
            for row in location_totals:
                if not row['location__name']:
                    continue
                capacity = self._decimal(row['location__capacity'] or Decimal('0'))
                current = self._decimal(row['current'] or Decimal('0'))
                ratio = (current / capacity) if capacity else Decimal('0')
                status, status_label = self._storage_status(ratio)
                storage_rows.append({
                    'location': row['location__name'],
                    'type': (row['location__location_type'] or '').replace('_', ' ').title(),
                    'capacity': self._format_number(capacity),
                    'current': self._format_number(current),
                    'fill': self._percent_of(current, capacity) if capacity else '0%',
                    'status': status,
                    'status_label': status_label,
                })

            today = timezone.now().date()
            cutoff = today + timedelta(days=7)
            alert_qs = storage_queryset.filter(expiry_date__lte=cutoff).order_by('expiry_date')[:10]
            for lot in alert_qs:
                days_left = (lot.expiry_date - today).days
                status = 'critical' if lot.status == 'expired' or days_left < 0 else 'warning'
                status_label = 'Expired' if status == 'critical' else 'Near expiry'
                storage_alerts.append({
                    'storage_id': lot.storage_id,
                    'product': lot.product,
                    'location': lot.location.name if lot.location else '—',
                    'expiry': lot.expiry_date,
                    'days_left': days_left,
                    'quantity': self._format_number(lot.quantity),
                    'status': status,
                    'status_label': status_label,
                })

        return {
            'stock': stock_rows,
            'reorder': reorder_rows,
            'wastage': wastage_rows,
            'delivery': delivery_rows,
            'storage': storage_rows,
            'storage_alerts': storage_alerts,
        }

    def _storage_status(self, ratio):
        if ratio >= Decimal('1'):
            return 'critical', 'Over capacity'
        if ratio >= Decimal('0.85'):
            return 'warning', 'Almost full'
        if ratio <= Decimal('0.2'):
            return 'warning', 'Underutilized'
        return 'good', 'Balanced'

    def _inventory_status(self, item):
        if item.current_quantity <= 0:
            return 'critical', 'Out of stock'
        if item.needs_reorder:
            return 'warning', 'Below threshold'
        if item.is_near_expiry:
            return 'warning', 'Near expiry'
        return 'good', 'Healthy'

    def _coverage_label(self, item):
        threshold = self._decimal(item.reorder_threshold)
        if threshold == 0:
            return 'N/A'
        ratio = self._decimal(item.current_quantity) / threshold
        days = max(1, int(ratio * 2))
        return f"{days} days"

    def _build_sales_reports(self, sales_queryset, sales_items):
        daily_rows = []
        daily_stats = (
            sales_queryset
            .annotate(period=TruncDate('created_at'))
            .values('period')
            .annotate(
                revenue=Sum('total_amount'),
                transactions=Count('id'),
                cash_total=Sum('total_amount', filter=Q(payment_mode='cash')),
            )
            .order_by('-period')[:10]
        )
        for row in daily_stats:
            revenue = self._decimal(row['revenue'])
            status, status_label = self._banding_status(revenue, 20000, 50000)
            daily_rows.append({
                'date': row['period'],
                'transactions': row['transactions'],
                'revenue': self._format_currency(revenue),
                'cash_ratio': self._percent_of(row['cash_total'], revenue),
                'status': status,
                'status_label': status_label,
            })

        revenue_expression = ExpressionWrapper(
            F('quantity') * F('price_per_unit'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        product_rows = []
        product_stats = (
            sales_items
            .values('inventory_item__sku', 'inventory_item__name')
            .annotate(units=Sum('quantity'), revenue=Sum(revenue_expression))
            .order_by('-revenue')[:10]
        )
        for row in product_stats:
            revenue = self._decimal(row['revenue'])
            units = self._decimal(row['units'])
            margin_ratio = Decimal('0.35') if revenue else Decimal('0')
            status, status_label = self._banding_status(units, 50, 150)
            product_rows.append({
                'sku': row['inventory_item__sku'] or row['inventory_item__name'],
                'units': self._format_number(units),
                'revenue': self._format_currency(revenue),
                'margin': f"{(margin_ratio * Decimal('100')).quantize(Decimal('0.1'))}%",
                'status': status,
                'status_label': status_label,
            })

        customer_rows = []
        customer_stats = (
            sales_queryset
            .filter(customer__isnull=False)
            .values('customer_id', 'customer__name', 'customer__loyalty_points')
            .annotate(orders=Count('id'), revenue=Sum('total_amount'))
            .order_by('-revenue')[:8]
        )
        for row in customer_stats:
            preference = sales_items.filter(transaction__customer_id=row['customer_id']).values('inventory_item__name').annotate(total=Sum('quantity')).order_by('-total').first()
            ratio = self._percent_of(row['customer__loyalty_points'] or 0, 1000)
            customer_rows.append({
                'customer': row['customer__name'],
                'orders': row['orders'],
                'revenue': self._format_currency(row['revenue']),
                'loyalty': f"{row['customer__loyalty_points']} pts",
                'status': 'good' if row['orders'] >= 3 else 'warning',
                'status_label': ratio,
                'preference': preference['inventory_item__name'] if preference else 'Mixed',
            })

        financial_rows = []
        financial_stats = (
            sales_queryset
            .annotate(period=TruncMonth('created_at'))
            .values('period')
            .annotate(revenue=Sum('total_amount'))
            .order_by('-period')[:6]
        )
        for row in financial_stats:
            revenue = self._decimal(row['revenue'])
            expenses = revenue * Decimal('0.62')
            profit = revenue - expenses
            status, status_label = self._banding_status(profit, 10000, 30000)
            financial_rows.append({
                'period': row['period'].strftime('%b %Y') if row['period'] else 'Month',
                'revenue': self._format_currency(revenue),
                'expenses': self._format_currency(expenses),
                'profit': self._format_currency(profit),
                'status': status,
                'status_label': status_label,
            })

        cash_rows = []
        cash_stats = (
            sales_queryset
            .annotate(period=TruncDate('created_at'))
            .values('period')
            .annotate(
                recorded=Sum('total_amount'),
                cash_total=Sum('total_amount', filter=Q(payment_mode='cash')),
            )
            .order_by('-period')[:10]
        )
        for row in cash_stats:
            recorded = self._decimal(row['recorded'])
            counted = self._decimal(row['cash_total'])
            difference = recorded - counted
            status = 'good' if difference == 0 else 'warning'
            cash_rows.append({
                'date': row['period'],
                'recorded': self._format_currency(recorded),
                'counted': self._format_currency(counted),
                'difference': self._format_currency(difference),
                'status': status,
                'status_label': 'Balanced' if status == 'good' else 'Investigate',
            })

        return {
            'daily': daily_rows,
            'product': product_rows,
            'customers': customer_rows,
            'financials': financial_rows,
            'cash': cash_rows,
        }

    def _build_relationship_reports(self, sales_queryset, sales_items, supplier_orders, price_changes):
        purchase_rows = []
        customer_stats = (
            sales_queryset
            .filter(customer__isnull=False)
            .values('customer_id', 'customer__name', 'customer__loyalty_points')
            .annotate(orders=Count('id'), revenue=Sum('total_amount'))
            .order_by('-orders')[:6]
        )
        for row in customer_stats:
            favorite = sales_items.filter(transaction__customer_id=row['customer_id']).values('inventory_item__name').annotate(total=Sum('quantity')).order_by('-total').first()
            repeat_ratio = min(100, row['orders'] * 20)
            purchase_rows.append({
                'customer': row['customer__name'],
                'preference': favorite['inventory_item__name'] if favorite else 'Mixed Basket',
                'trend': repeat_ratio,
                'trend_label': f"▲ {row['orders']} repeat orders" if row['orders'] else 'No repeats yet',
            })

        promotion_rows = []
        for change in price_changes.select_related('product_price__inventory_item').order_by('-changed_at')[:6]:
            if not change.old_price:
                continue
            diff = self._decimal(change.new_price) - self._decimal(change.old_price)
            percent = self._percent_difference(change.new_price, change.old_price)
            status = 'good' if diff < 0 else 'warning'
            promotion_rows.append({
                'name': change.product_price.product_name,
                'uplift': percent,
                'status': status,
                'status_label': 'Boost' if status == 'good' else 'Monitor',
            })

        supplier_rows = []
        supplier_stats = (
            supplier_orders
            .values('supplier__name')
            .annotate(total=Count('id'), delivered=Count('id', filter=Q(status='delivered')))
        )
        for row in supplier_stats:
            score = self._percent_of(row['delivered'], row['total'])
            delivered_ratio = (self._decimal(row['delivered']) / self._decimal(row['total'])) if row['total'] else Decimal('0')
            status, status_label = self._status_from_ratio(delivered_ratio)
            supplier_rows.append({
                'supplier': row['supplier__name'],
                'score': score,
                'status': status,
                'status_label': status_label,
            })

        return {
            'purchase_history': purchase_rows,
            'promotions': promotion_rows,
            'suppliers': supplier_rows,
        }

    def _build_management_reports(self, milk_queryset, batch_queryset, sales_queryset, inventory_transactions, customer_interactions, supplier_orders):
        efficiency_rows = []
        efficiency_stats = (
            batch_queryset
            .annotate(period=TruncMonth('produced_at'))
            .values('period')
            .annotate(liters=Sum('liters_used'), units=Sum('quantity_produced'))
            .order_by('-period')[:6]
        )
        for row in efficiency_stats:
            liters = self._decimal(row['liters'])
            units = self._decimal(row['units'])
            ratio = (units / liters) if liters else Decimal('0')
            status, status_label = self._status_from_ratio(ratio)
            efficiency_rows.append({
                'period': row['period'].strftime('%b %Y') if row['period'] else 'Period',
                'liters': self._format_number(liters, ' L'),
                'units': self._format_number(units),
                'yield': self._percent_of(units, liters),
                'status': status,
                'status_label': status_label,
            })

        productivity_rows = []
        productivity_stats = (
            batch_queryset
            .values('processed_by__first_name', 'processed_by__last_name')
            .annotate(batches=Count('id'), exceptions=Count('id', filter=Q(moved_to_lab=False)))
            .order_by('-batches')[:8]
        )
        for row in productivity_stats:
            operator = (row['processed_by__first_name'] or '') + ' ' + (row['processed_by__last_name'] or '')
            status, status_label = self._banding_status(row['batches'], 2, 5)
            productivity_rows.append({
                'operator': operator.strip() or 'Operator',
                'batches': row['batches'],
                'exceptions': row['exceptions'],
                'status': status,
                'status_label': status_label,
            })

        usage_rows = []
        usage_sources = [
            ('Production', milk_queryset.count() + batch_queryset.count()),
            ('Inventory', inventory_transactions.count()),
            ('Sales', sales_queryset.count()),
            ('Customers', customer_interactions.count()),
            ('Suppliers', supplier_orders.count()),
        ]
        total_usage = sum(value for _, value in usage_sources) or 1
        for label, value in usage_sources:
            status, status_label = self._banding_status(value, total_usage * 0.15, total_usage * 0.25)
            usage_rows.append({
                'module': label,
                'sessions': value,
                'share': self._percent_of(value, total_usage),
                'status': status,
                'status_label': status_label,
            })

        forecasting_rows = []
        monthly_revenue = list(
            sales_queryset
            .annotate(period=TruncMonth('created_at'))
            .values('period')
            .annotate(revenue=Sum('total_amount'))
            .order_by('period')
        )
        if monthly_revenue:
            recent = monthly_revenue[-3:]
            total = sum(self._decimal(row['revenue']) for row in recent)
            average = total / len(recent)
            last_period = monthly_revenue[-1]['period']
            forecast_label = (last_period.strftime('%b %Y') if last_period else 'Next Period') + ' +1'
            confidence = min(95, 60 + len(recent) * 10)
            status = 'good' if recent[-1]['revenue'] <= average else 'warning'
            forecasting_rows.append({
                'period': forecast_label,
                'predicted': self._format_currency(average),
                'confidence': f"{confidence}%",
                'status': status,
                'status_label': 'Stable' if status == 'good' else 'Volatile',
            })

        return {
            'efficiency': efficiency_rows,
            'productivity': productivity_rows,
            'usage': usage_rows,
            'forecasting': forecasting_rows,
        }

    # ------------------------------------------------------------------
    # export helpers
    # ------------------------------------------------------------------
    def _collect_export_payload(self, module, report_key, report_slug, *module_reports):
        module_map = {
            'production': module_reports[0],
            'inventory': module_reports[1],
            'sales': module_reports[2],
            'relationship': module_reports[3],
            'management': module_reports[4],
        }
        normalized_module = module if module in module_map else ''
        selected_modules = [normalized_module] if normalized_module else list(module_map.keys())

        sections = []
        selected_report = None
        for mod in selected_modules:
            reports = module_map[mod]
            if report_key:
                if report_key in reports:
                    prepared = self._prepare_section(mod, report_key, reports[report_key])
                    if prepared:
                        sections.append(prepared)
                        selected_report = report_key
                        break
            else:
                for key, rows in reports.items():
                    prepared = self._prepare_section(mod, key, rows)
                    if prepared:
                        sections.append(prepared)

        if not sections:
            sections.append({
                'module': 'all',
                'report': 'empty',
                'title': 'No data available',
                'columns': ['Message'],
                'rows': [{'Message': 'No records found for the selected filters'}],
            })

        return {
            'sections': sections,
            'module': normalized_module or 'all',
            'report': selected_report or (report_key if report_key else 'all'),
            'report_slug': report_slug or selected_report or (report_key if report_key else 'all'),
        }

    def _prepare_section(self, module, report_key, rows):
        columns = self._derive_columns(rows)
        if not columns:
            columns = ['Info']
        return {
            'module': module,
            'report': report_key,
            'title': self._resolve_section_title(module, report_key),
            'columns': columns,
            'rows': rows,
        }

    def _derive_columns(self, rows):
        if not rows:
            return []
        for row in rows:
            if isinstance(row, dict):
                return list(row.keys())
        return []

    def _resolve_module_key(self, module):
        if not module:
            return ''
        key = module.strip().lower()
        return self.MODULE_ALIASES.get(key, key)

    def _normalize_module(self, module):
        key = self._resolve_module_key(module)
        return key if key in self.MODULE_TITLES else ''

    def _form_value_for_module(self, module_key):
        if not module_key:
            return ''
        return self.MODULE_FORM_PREFERENCES.get(module_key, module_key)

    def _resolve_report_target(self, report_key):
        if not report_key:
            return None, None, None
        key = report_key.strip().lower()
        if not key:
            return None, None, None
        if '.' in key:
            module_hint, report_hint = key.split('.', 1)
            normalized_module = self._normalize_module(module_hint)
            if normalized_module and report_hint in self.REPORT_LABELS.get(normalized_module, {}):
                return normalized_module, report_hint, key
        alias = self.REPORT_ALIAS_MAP.get(key)
        if alias:
            return alias[0], alias[1], key
        return None, None, key

    def _resolve_section_title(self, module, report_key):
        module_label = self.MODULE_TITLES.get(module, module.title() if module else 'All Modules')
        report_label = self.REPORT_LABELS.get(module, {}).get(report_key, report_key.replace('_', ' ').title())
        return f"{module_label} · {report_label}"

    def _module_label(self, module_key):
        if not module_key or module_key == 'all':
            return 'All Modules'
        return self.MODULE_TITLES.get(module_key, module_key.title())

    def _slugify(self, value, fallback='all'):
        if not value:
            return fallback
        slug = ''.join(ch.lower() if ch.isalnum() else '-' for ch in str(value))
        slug = '-'.join(filter(None, slug.split('-')))
        return slug or fallback

    def _export_excel(self, payload, start_date, end_date):
        try:
            from openpyxl import Workbook
        except ImportError as exc:
            raise ImproperlyConfigured('openpyxl is required for Excel exports. Install it via pip install openpyxl.') from exc

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = 'Reports'
        worksheet.append([f"Nawasons Reports • {self._module_label(payload['module'])}"])
        worksheet.append([self._date_range_label(start_date, end_date)])
        worksheet.append([])

        for section in payload['sections']:
            worksheet.append([section['title']])
            columns = section['columns'] or ['Info']
            worksheet.append(columns)
            if section['rows']:
                for row in section['rows']:
                    worksheet.append([self._clean_export_value(row.get(col, '')) for col in columns])
            else:
                worksheet.append(['No data available for this report'])
            worksheet.append([])

        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        filename = self._default_filename('xlsx', payload['module'], payload['report_slug'], start_date, end_date)
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def _export_pdf(self, payload, start_date, end_date):
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError as exc:
            raise ImproperlyConfigured('reportlab is required for PDF exports. Install it via pip install reportlab.') from exc

        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
        )
        styles = getSampleStyleSheet()
        elements = []
        elements.append(Paragraph(f"Nawasons Reports • {self._module_label(payload['module'])}", styles['Title']))
        elements.append(Paragraph(self._date_range_label(start_date, end_date), styles['Normal']))
        elements.append(Spacer(1, 8))

        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
        ])

        for section in payload['sections']:
            elements.append(Paragraph(section['title'], styles['Heading2']))
            columns = section['columns'] or ['Info']
            data = [columns]
            if section['rows']:
                for row in section['rows']:
                    data.append([str(row.get(col, '')) for col in columns])
            else:
                data.append(['No data available for this report'])
            table = Table(data, repeatRows=1)
            table.setStyle(table_style)
            elements.append(table)
            elements.append(Spacer(1, 10))

        document.build(elements)
        buffer.seek(0)
        filename = self._default_filename('pdf', payload['module'], payload['report_slug'], start_date, end_date)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def _date_range_label(self, start_date, end_date):
        if start_date and end_date:
            return f"Range: {start_date:%Y-%m-%d} → {end_date:%Y-%m-%d}"
        if start_date:
            return f"From {start_date:%Y-%m-%d} onwards"
        if end_date:
            return f"Up to {end_date:%Y-%m-%d}"
        return f"Generated {timezone.now():%Y-%m-%d}"

    def _default_filename(self, extension, module_key, report_key_slug, start_date, end_date):
        module_slug = self._slugify(module_key, 'all')
        report_slug = self._slugify(report_key_slug, 'all')
        if start_date and end_date:
            date_slug = f"{start_date:%Y%m%d}-{end_date:%Y%m%d}"
        elif start_date:
            date_slug = f"from-{start_date:%Y%m%d}"
        elif end_date:
            date_slug = f"through-{end_date:%Y%m%d}"
        else:
            date_slug = timezone.now().strftime('%Y%m%d')
        return f"reports-{module_slug}-{report_slug}-{date_slug}.{extension}"

    def _clean_export_value(self, value):
        if value is None:
            return ''
        if isinstance(value, Decimal):
            return float(value)
        if hasattr(value, 'isoformat'):
            try:
                return value.isoformat()
            except Exception:
                return str(value)
        return value

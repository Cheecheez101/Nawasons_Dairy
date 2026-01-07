from decimal import Decimal
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from openpyxl import Workbook

from inventory.models import InventoryItem
from .forms import CowForm, MilkYieldForm, ProductPriceForm, ProductionBatchForm
from .models import Cow, MilkYield, ProductPrice, ProductionBatch


def _filtered_yield_queryset(request):
    qs = MilkYield.objects.select_related("cow")
    filters = {
        "session": (request.GET.get("session") or "").strip(),
        "search": (request.GET.get("q") or "").strip(),
        "date_from": (request.GET.get("date_from") or "").strip(),
        "date_to": (request.GET.get("date_to") or "").strip(),
    }

    if filters["session"]:
        qs = qs.filter(session=filters["session"])
    if filters["search"]:
        term = filters["search"]
        qs = qs.filter(Q(cow__cow_id__icontains=term) | Q(cow__name__icontains=term))
    date_from = parse_date(filters["date_from"]) if filters["date_from"] else None
    if date_from:
        qs = qs.filter(recorded_at__date__gte=date_from)
    date_to = parse_date(filters["date_to"]) if filters["date_to"] else None
    if date_to:
        qs = qs.filter(recorded_at__date__lte=date_to)

    return qs.order_by("-recorded_at"), filters


class CowListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.view_cow'

    def get(self, request):
        today = timezone.now().date()
        cows = Cow.objects.prefetch_related('yields').annotate(
            today_yield=Sum(
                'yields__yield_litres',
                filter=Q(yields__recorded_at__date=today)
            )
        ).all()
        
        # Apply cow filters
        cow_search = request.GET.get('cow_q', '').strip()
        if cow_search:
            cows = cows.filter(
                Q(name__icontains=cow_search) | Q(cow_id__icontains=cow_search)
            )
        
        breed = request.GET.get('breed', '').strip()
        if breed:
            cows = cows.filter(breed__iexact=breed)
        
        health = request.GET.get('health', '').strip()
        if health:
            cows = cows.filter(health_status=health)
        
        is_active = request.GET.get('is_active', '').strip()
        if is_active == '1':
            cows = cows.filter(is_active=True)
        elif is_active == '0':
            cows = cows.filter(is_active=False)
        
        yield_qs, filter_values = _filtered_yield_queryset(request)
        yield_totals = yield_qs.aggregate(total_volume=Sum('yield_litres'))
        yield_summary = {
            'count': yield_qs.count(),
            'volume': yield_totals.get('total_volume') or Decimal('0'),
        }
        context = {
            'cows': cows,
            'yield_rows': yield_qs,
            'filters': filter_values,
            'session_choices': MilkYield.SESSION_CHOICES,
            'yield_summary': yield_summary,
        }
        return render(request, 'production/cow_list.html', context)


class MilkYieldCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.add_milkyield'

    def get(self, request):
        return render(request, 'production/yield_form.html', {'form': MilkYieldForm()})

    def post(self, request):
        form = MilkYieldForm(request.POST)
        if form.is_valid():
            yield_entry = form.save(commit=False)
            yield_entry.recorded_by = request.user
            yield_entry.save()
            messages.success(request, f'Milk yield for {yield_entry.cow.name or yield_entry.cow.cow_id} recorded: {yield_entry.yield_litres} L')
            return redirect('production:yield_create')
        return render(request, 'production/yield_form.html', {'form': form})


class MilkYieldUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.change_milkyield'

    def get(self, request, pk):
        yield_entry = get_object_or_404(MilkYield, pk=pk)
        form = MilkYieldForm(instance=yield_entry)
        return render(request, 'production/yield_form.html', {'form': form, 'yield_entry': yield_entry})

    def post(self, request, pk):
        yield_entry = get_object_or_404(MilkYield, pk=pk)
        form = MilkYieldForm(request.POST, instance=yield_entry)
        if form.is_valid():
            form.save()
            messages.success(request, 'Milk yield updated successfully.')
            return redirect('production:cow_list')
        return render(request, 'production/yield_form.html', {'form': form, 'yield_entry': yield_entry})


class MilkYieldDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.delete_milkyield'

    def post(self, request, pk):
        yield_entry = get_object_or_404(MilkYield, pk=pk)
        yield_entry.delete()
        messages.success(request, 'Milk yield entry deleted.')
        return redirect('production:cow_list')


class MilkYieldExportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.view_milkyield'

    def get(self, request):
        yield_qs, _ = _filtered_yield_queryset(request)
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = 'Milk Yields'
        worksheet.append([
            'Milk clerk',
            'Cow name',
            'Cow ID',
            'Breed',
            'Session',
            'Recorded at',
            'Yield (L)',
            'Tank',
        ])

        for entry in yield_qs:
            clerk = getattr(entry, 'recorded_by', None)
            if clerk:
                clerk_name = clerk.get_full_name() or clerk.get_username()
            else:
                clerk_name = ''
            recorded_at = entry.recorded_at
            if recorded_at:
                if timezone.is_naive(recorded_at):
                    timestamp = recorded_at.strftime('%Y-%m-%d %H:%M')
                else:
                    timestamp = timezone.localtime(recorded_at).strftime('%Y-%m-%d %H:%M')
            else:
                timestamp = ''

            worksheet.append([
                clerk_name,
                entry.cow.name or '',
                entry.cow.cow_id,
                entry.cow.breed,
                entry.get_session_display(),
                timestamp,
                float(entry.yield_litres),
                entry.storage_tank,
            ])

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"milk-yields-{timezone.now():%Y%m%d-%H%M}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        workbook.save(response)
        return response


class CowCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.add_cow'

    def get(self, request):
        return render(request, 'production/cow_form.html', {'form': CowForm()})

    def post(self, request):
        form = CowForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('production:cow_list')
        return render(request, 'production/cow_form.html', {'form': form})


class CowUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.change_cow'

    def get(self, request, pk):
        cow = get_object_or_404(Cow, pk=pk)
        form = CowForm(instance=cow)
        return render(request, 'production/cow_form.html', {'form': form, 'cow': cow})

    def post(self, request, pk):
        cow = get_object_or_404(Cow, pk=pk)
        form = CowForm(request.POST, instance=cow)
        if form.is_valid():
            form.save()
            messages.success(request, f'Cow {cow.name or cow.cow_id} updated successfully.')
            return redirect('production:cow_list')
        return render(request, 'production/cow_form.html', {'form': form, 'cow': cow})


class CowDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.delete_cow'

    def post(self, request, pk):
        cow = get_object_or_404(Cow, pk=pk)
        cow_name = cow.name or cow.cow_id
        cow.delete()
        messages.success(request, f'Cow {cow_name} deleted successfully.')
        return redirect('production:cow_list')


class MilkApprovalView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.approve_milk'

    def post(self, request, pk):
        yield_entry = get_object_or_404(MilkYield, pk=pk)
        action = request.POST.get('action')
        if action == 'approve':
            yield_entry.quality_grade = 'premium'
        elif action == 'reject':
            yield_entry.quality_grade = 'low'
        yield_entry.save(update_fields=['quality_grade'])
        return redirect('production:cow_list')


class ProductPriceListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.view_productprice'

    def get(self, request):
        prices = ProductPrice.objects.select_related('inventory_item', 'updated_by')
        
        # Apply filters
        search = request.GET.get('q', '').strip()
        if search:
            prices = prices.filter(
                Q(product_name__icontains=search) | Q(sku__icontains=search)
            )
        
        price_min = request.GET.get('price_min', '').strip()
        if price_min:
            try:
                prices = prices.filter(price__gte=Decimal(price_min))
            except (ValueError, TypeError):
                pass
        
        price_max = request.GET.get('price_max', '').strip()
        if price_max:
            try:
                prices = prices.filter(price__lte=Decimal(price_max))
            except (ValueError, TypeError):
                pass
        
        return render(request, 'production/price_list.html', {'prices': prices})


class ProductPriceCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.add_productprice'

    def get(self, request):
        return render(request, 'production/price_form.html', {'form': ProductPriceForm()})

    def post(self, request):
        form = ProductPriceForm(request.POST)
        if form.is_valid():
            price = form.save(commit=False)
            price.updated_by = request.user
            price.save()
            messages.success(request, 'Price created successfully.')
            return redirect('production:price_list')
        return render(request, 'production/price_form.html', {'form': form})


class ProductPriceUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.change_productprice'

    def get(self, request, pk):
        price = get_object_or_404(ProductPrice, pk=pk)
        form = ProductPriceForm(instance=price)
        return render(request, 'production/price_form.html', {'form': form, 'price': price})

    def post(self, request, pk):
        price = get_object_or_404(ProductPrice, pk=pk)
        form = ProductPriceForm(request.POST, instance=price)
        if form.is_valid():
            price = form.save(commit=False)
            price.updated_by = request.user
            price.save()
            messages.success(request, 'Price updated successfully.')
            return redirect('production:price_list')
        return render(request, 'production/price_form.html', {'form': form, 'price': price})


class ProductionBatchListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.view_productionbatch'

    def get(self, request):
        batches = ProductionBatch.objects.select_related('processed_by').order_by('-produced_at')
        
        # Apply filters
        product_type = request.GET.get('product_type', '').strip()
        if product_type:
            batches = batches.filter(product_type=product_type)
        
        source_tank = request.GET.get('source_tank', '').strip()
        if source_tank:
            batches = batches.filter(source_tank__icontains=source_tank)
        
        date_from = request.GET.get('date_from', '').strip()
        if date_from:
            batches = batches.filter(produced_at__date__gte=parse_date(date_from))
        
        date_to = request.GET.get('date_to', '').strip()
        if date_to:
            batches = batches.filter(produced_at__date__lte=parse_date(date_to))
        
        return render(request, 'production/batch_list.html', {'batches': batches})


def batch_form(request):
    if request.method == 'POST':
        form = ProductionBatchForm(request.POST)
        if form.is_valid():
            batch = form.save(commit=False)
            batch.processed_by = request.user
            try:
                batch.consume_milk()
                batch.save()
                messages.success(request, "Production batch created successfully. Milk deducted from tank.")
                return redirect('production:batch_list')
            except Exception as e:
                messages.error(request, f"Error creating batch: {e}")
    else:
        form = ProductionBatchForm()

    # Prepare SKU data for dynamic filtering
    items = InventoryItem.objects.all()
    sku_data = {}
    for item in items:
        cat = item.product_category
        if cat not in sku_data:
            sku_data[cat] = []
        sku_data[cat].append({
            'sku': item.sku,
            'name': f"{item.name} ({item.sku})",
            'size': item.size_ml or 0
        })

    # Get tank information with total milk in each tank
    from lab.models import MilkYield
    tanks_info = []
    for tank_name in MilkYield.TANK_CAPACITY_LITRES.keys():
        if tank_name != 'Unassigned':
            total_litres = MilkYield.objects.filter(storage_tank=tank_name).aggregate(Sum('yield_litres'))['yield_litres__sum'] or 0
            capacity = MilkYield.TANK_CAPACITY_LITRES[tank_name]
            tanks_info.append({
                'name': tank_name,
                'total_litres': float(total_litres),
                'capacity_litres': float(capacity),
                'percentage': (float(total_litres) / float(capacity) * 100) if capacity > 0 else 0
            })

    return render(request, "production/batch_form.html", {
        "form": form,
        "sku_data_json": json.dumps(sku_data),
        "tanks_info": tanks_info
    })

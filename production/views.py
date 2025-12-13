from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from .models import Cow, MilkYield, ProductPrice, ProductionBatch
from .forms import MilkYieldForm, CowForm, ProductPriceForm, ProductionBatchForm


class CowListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.view_cow'

    def get(self, request):
        cows = Cow.objects.prefetch_related('yields').all()
        return render(request, 'production/cow_list.html', {'cows': cows})


class MilkYieldCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.add_milkyield'

    def get(self, request):
        return render(request, 'production/yield_form.html', {'form': MilkYieldForm()})

    def post(self, request):
        form = MilkYieldForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('production:cow_list')
        return render(request, 'production/yield_form.html', {'form': form})


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


# Function-based view for batch creation with optional preselected tank
def batch_form(request):
    initial = {}
    preselect = request.GET.get('tank')
    if preselect:
        # If preselect looks like an integer, try to treat it as a MilkYield PK
        try:
            pk = int(preselect)
        except (TypeError, ValueError):
            pk = None

        if pk:
            try:
                initial['milk_source'] = MilkYield.objects.get(pk=pk)
            except MilkYield.DoesNotExist:
                pass
        else:
            # treat preselect as a storage_tank name; pick the first approved yield in that tank
            try:
                my = (
                    MilkYield.objects.filter(storage_tank=preselect, raw_test_approved=True)
                    .order_by('recorded_at')
                    .first()
                )
                if my:
                    initial['milk_source'] = my
            except Exception:
                pass
    if request.method == "POST":
        form = ProductionBatchForm(request.POST)
        if form.is_valid():
            batch = form.save(commit=False)
            batch.processed_by = request.user
            try:
                batch.consume_milk()
                batch.save()
                messages.success(request, "Production batch created successfully. Milk deducted from tank.")
                return redirect('lab:milk_yield_tests', yield_id=batch.milk_source.id)
            except Exception as e:
                messages.error(request, f"Error creating batch: {e}")
    else:
        form = ProductionBatchForm(initial=initial)
    return render(request, "production/batch_form.html", {"form": form})

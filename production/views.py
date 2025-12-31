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


class ProductionBatchListView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'production.view_productionbatch'

    def get(self, request):
        batches = ProductionBatch.objects.select_related('processed_by').order_by('-produced_at')
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
    return render(request, "production/batch_form.html", {"form": form})

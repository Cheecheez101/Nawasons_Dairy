from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponse
from django.db.models import Sum, Max, Q
from .models import Customer
from .forms import CustomerForm, LoyaltyAdjustmentForm

class CustomerDashboardView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'customers.view_customer'

    def get(self, request):
        customers = Customer.objects.annotate(
            total_spend=Sum('sales__total_amount'),
            last_purchase=Max('sales__created_at')
        )
        
        # Apply filters
        search = request.GET.get('q', '').strip()
        if search:
            customers = customers.filter(
                Q(name__icontains=search) | Q(phone__icontains=search)
            )
        
        min_points = request.GET.get('min_points', '').strip()
        if min_points:
            try:
                customers = customers.filter(loyalty_points__gte=int(min_points))
            except (ValueError, TypeError):
                pass
        
        min_spend = request.GET.get('min_spend', '').strip()
        if min_spend:
            try:
                customers = customers.filter(total_spend__gte=float(min_spend))
            except (ValueError, TypeError):
                pass
        
        has_purchase = request.GET.get('has_purchase', '').strip()
        if has_purchase == 'yes':
            customers = customers.filter(last_purchase__isnull=False)
        elif has_purchase == 'no':
            customers = customers.filter(last_purchase__isnull=True)
        
        return render(request, 'customers/dashboard.html', {'customers': customers})

class CustomerCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'customers.add_customer'

    def get(self, request):
        return render(request, 'customers/form.html', {'form': CustomerForm()})

    def post(self, request):
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('customers:index')
        return render(request, 'customers/form.html', {'form': form})

class CustomerUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'customers.change_customer'

    def get(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        return render(request, 'customers/form.html', {'form': CustomerForm(instance=customer), 'customer': customer})

    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            return redirect('customers:index')
        return render(request, 'customers/form.html', {'form': form, 'customer': customer})

class LoyaltyAdjustView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'customers.change_customer'

    def get(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        return render(request, 'customers/loyalty.html', {'form': LoyaltyAdjustmentForm(), 'customer': customer})

    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        form = LoyaltyAdjustmentForm(request.POST)
        if form.is_valid():
            customer.loyalty_points = max(0, customer.loyalty_points + form.cleaned_data['points'])
            customer.save(update_fields=['loyalty_points'])
            return redirect('customers:index')
        return render(request, 'customers/loyalty.html', {'form': form, 'customer': customer})

class LoyaltyExportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'customers.view_customer'

    def get(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        rows = ['Date,Reason,Points Change,Balance After']
        for entry in customer.loyalty_ledger.all():
            rows.append(f"{entry.created_at:%Y-%m-%d %H:%M},{entry.reason},{entry.points_change},{entry.balance_after}")
        response = HttpResponse('\n'.join(rows), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="loyalty_{customer.pk}.csv"'
        return response

class CustomerDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'customers.delete_customer'

    def get(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        return render(request, 'customers/confirm_delete.html', {'customer': customer})

    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        customer.delete()
        return redirect('customers:index')

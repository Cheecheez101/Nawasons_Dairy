from django.shortcuts import render, redirect, get_object_or_404
from .models import Seller, SellerTransaction
from .forms import SellerForm, SellerTransactionForm
from inventory.models import InventoryItem
from storage.models import Packaging
from django.db.models import Sum, F, Q
from django.utils import timezone


def _apply_bootstrap_classes(form):
    """Ensure all form fields render with Bootstrap form-control styling."""
    for name, field in form.fields.items():
        classes = field.widget.attrs.get('class', '')
        # prefer small inputs for compact forms
        if 'form-control' not in classes:
            classes = (classes + ' form-control').strip()
        field.widget.attrs['class'] = classes

def add_seller(request):
    if request.method == 'POST':
        form = SellerForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('seller_list')
    else:
        form = SellerForm()
    _apply_bootstrap_classes(form)
    return render(request, 'sellers/serve_seller.html', {'form': form, 'add_seller': True})

def serve_seller(request):
    if request.method == 'POST':
        form = SellerTransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save()
            # Deduct from inventory
            item = transaction.product
            item.current_quantity = F('current_quantity') - transaction.quantity
            item.save()
            return redirect('seller_transactions')
    else:
        form = SellerTransactionForm()
    _apply_bootstrap_classes(form)
    return render(request, 'sellers/serve_seller.html', {'form': form, 'add_seller': False})

def seller_list(request):
    sellers = Seller.objects.all()
    return render(request, 'sellers/seller_list.html', {'sellers': sellers})

def seller_transactions(request):
    sellers = Seller.objects.all()
    products = InventoryItem.objects.all()
    transactions = SellerTransaction.objects.select_related('seller', 'product', 'packaging')
    seller_id = request.GET.get('seller')
    product_id = request.GET.get('product')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if seller_id:
        transactions = transactions.filter(seller_id=seller_id)
    if product_id:
        transactions = transactions.filter(product_id=product_id)
    if start_date:
        transactions = transactions.filter(transaction_date__gte=start_date)
    if end_date:
        transactions = transactions.filter(transaction_date__lte=end_date)
    return render(request, 'sellers/seller_transactions.html', {
        'transactions': transactions,
        'sellers': sellers,
        'products': products,
    })

def seller_distribution_report(request):
    report = SellerTransaction.objects.values('seller__name').annotate(total=Sum('quantity')).order_by('-total')
    return render(request, 'sellers/seller_distribution_report.html', {'report': report})

def seller_product_report(request):
    report = SellerTransaction.objects.values('seller__name', 'product__name').annotate(total=Sum('quantity')).order_by('seller__name', 'product__name')
    return render(request, 'sellers/seller_product_report.html', {'report': report})

def combined_inventory_impact_report(request):
    from sales.models import SalesTransaction
    # Sales items are stored in SalesItem, which references InventoryItem as `inventory_item`.
    from sales.models import SalesItem
    sales = SalesItem.objects.values('inventory_item__name').annotate(total=Sum('quantity'))
    sellers = SellerTransaction.objects.values('product__name').annotate(total=Sum('quantity'))
    # Combine by product name. keys differ between querysets, normalize safely.
    combined = {}
    for s in sales:
        name = s.get('inventory_item__name') or s.get('product__name')
        if not name:
            continue
        combined[name] = {'sales': s['total'], 'sellers': 0}
    for t in sellers:
        name = t.get('product__name') or t.get('inventory_item__name')
        if not name:
            continue
        if name in combined:
            combined[name]['sellers'] = t['total']
        else:
            combined[name] = {'sales': 0, 'sellers': t['total']}

    # Convert to list for simpler template rendering
    combined_list = [
        {'product': name, 'sales': vals['sales'], 'sellers': vals['sellers']}
        for name, vals in combined.items()
    ]
    return render(request, 'sellers/combined_inventory_impact_report.html', {'combined': combined_list})

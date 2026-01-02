import io

from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.forms import formset_factory
from django.http import HttpResponse
from django.db.models import Q, CharField
from django.db.models.functions import Cast

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph

from .forms import SalesTransactionForm, SalesItemForm
from .models import SalesTransaction, SalesItem
from inventory.models import InventoryItem
from storage.services import adjust_storage_for_inventory_item
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.utils import timezone
from production.models import ProductPrice
from customers.models import Customer, LoyaltyTier


class SalesDashboardView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.view_salestransaction'

    def get(self, request):
        queryset = SalesTransaction.objects.select_related('customer').order_by('-created_at')
        queryset = self._apply_filters(queryset, request)
        export = (request.GET.get('export') or '').lower()
        if export == 'pdf':
            return self._export_pdf(queryset)
        if export == 'excel':
            return self._export_excel(queryset)
        transactions = list(queryset[:20])
        return render(request, 'sales/dashboard.html', {'transactions': transactions})

    def _apply_filters(self, queryset, request):
        filters = {
            'transaction_id': (request.GET.get('filter__transaction_id') or '').strip(),
            'customer': (request.GET.get('filter__customer') or '').strip(),
            'total_amount': (request.GET.get('filter__total_amount') or '').strip(),
            'payment_status': (request.GET.get('filter__payment_status') or '').strip(),
            'created_at': (request.GET.get('filter__created_at') or '').strip(),
        }
        if filters['transaction_id']:
            queryset = queryset.filter(transaction_id__icontains=filters['transaction_id'])
        if filters['customer']:
            value = filters['customer']
            queryset = queryset.filter(
                Q(customer__name__icontains=value) |
                Q(walk_in_customer_name__icontains=value) |
                Q(customer_phone__icontains=value)
            )
        if filters['total_amount']:
            queryset = queryset.annotate(_total_str=Cast('total_amount', CharField())).filter(_total_str__icontains=filters['total_amount'])
        if filters['payment_status']:
            queryset = queryset.filter(payment_status__icontains=filters['payment_status'])
        if filters['created_at']:
            queryset = queryset.annotate(_created_str=Cast('created_at', CharField())).filter(_created_str__icontains=filters['created_at'])
        return queryset

    def _export_excel(self, queryset):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Sales'
        headers = ['Transaction ID', 'Customer', 'Total Amount', 'Payment Status', 'Payment Mode', 'Created At']
        sheet.append(headers)
        for tx in queryset:
            sheet.append([
                tx.transaction_id,
                tx.customer_display_name,
                float(tx.total_amount or 0),
                tx.get_payment_status_display(),
                tx.get_payment_mode_display(),
                timezone.localtime(tx.created_at).strftime('%Y-%m-%d %H:%M'),
            ])
        for idx, _ in enumerate(headers, start=1):
            sheet.column_dimensions[get_column_letter(idx)].width = 20
        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        timestamp = timezone.now().strftime('%Y%m%d-%H%M%S')
        response = HttpResponse(buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="sales-{timestamp}.xlsx"'
        return response

    def _export_pdf(self, queryset):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), title='Sales Export')
        styles = getSampleStyleSheet()
        data = [[
            'Transaction ID',
            'Customer',
            'Total Amount',
            'Payment Status',
            'Payment Mode',
            'Created At',
        ]]
        for tx in queryset:
            data.append([
                tx.transaction_id,
                tx.customer_display_name,
                f"KES {tx.total_amount:.2f}",
                tx.get_payment_status_display(),
                tx.get_payment_mode_display(),
                timezone.localtime(tx.created_at).strftime('%Y-%m-%d %H:%M'),
            ])
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F2F2F2')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#DDDDDD')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FBFBFB')]),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        title = Paragraph('Sales Export', styles['Title'])
        doc.build([title, table])
        pdf_value = buffer.getvalue()
        buffer.close()
        timestamp = timezone.now().strftime('%Y%m%d-%H%M%S')
        response = HttpResponse(pdf_value, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="sales-{timestamp}.pdf"'
        return response

class SalesCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.add_salestransaction'
    SalesItemFormSet = formset_factory(SalesItemForm, extra=1)

    def get(self, request):
        form = SalesTransactionForm()
        formset = self.SalesItemFormSet()
        return render(request, 'sales/create.html', {'form': form, 'formset': formset})

    def _resolve_price(self, inventory_item, request):
        product_price = ProductPrice.current_for_inventory(inventory_item)
        if product_price:
            return product_price.price
        messages.warning(
            request,
            f"No ProductPrice found for {inventory_item.name}. Falling back to inventory default price.",
        )
        return inventory_item.default_price

    def post(self, request):
        form = SalesTransactionForm(request.POST)
        formset = self.SalesItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            transaction = form.save()
            total = 0
            for item_form in formset:
                if item_form.cleaned_data:
                    inventory_item = item_form.cleaned_data['inventory_item']
                    quantity = item_form.cleaned_data['quantity']
                    price = self._resolve_price(inventory_item, request)
                    SalesItem.objects.create(
                        transaction=transaction,
                        inventory_item=inventory_item,
                        quantity=quantity,
                        price_per_unit=price,
                    )
                    inventory_item.current_quantity -= quantity
                    inventory_item.save(update_fields=['current_quantity'])
                    adjust_storage_for_inventory_item(inventory_item, -quantity)
                    total += quantity * price
            transaction.total_amount = total
            transaction.save(update_fields=['total_amount'])
            if transaction.customer and total:
                points_earned = LoyaltyTier.points_for_amount(total)
                if points_earned:
                    customer = transaction.customer
                    customer.loyalty_points += points_earned
                    customer.save(update_fields=['loyalty_points'])
                    customer.loyalty_ledger.create(
                        points_change=points_earned,
                        balance_after=customer.loyalty_points,
                        reason=f"Purchase {transaction.transaction_id} ({total:.2f})"
                    )
            return redirect('sales:dashboard')
        return render(request, 'sales/create.html', {'form': form, 'formset': formset})

class SalesReceiptView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.view_salestransaction'

    def get(self, request, pk):
        transaction = SalesTransaction.objects.prefetch_related('items__inventory_item').get(pk=pk)
        items = list(transaction.items.all())
        subtotal = sum((item.line_total for item in items), Decimal('0.00'))
        discount_amount = subtotal - transaction.total_amount if subtotal > transaction.total_amount else Decimal('0.00')
        tax_amount = Decimal('0.00')

        def resolve_user_name(user):
            if not user:
                return None
            full_name = user.get_full_name() if hasattr(user, 'get_full_name') else ''
            return full_name or getattr(user, 'username', None)

        def resolve_job_title(user):
            if not user:
                return None
            profile = getattr(user, 'profile', None)
            job_title = getattr(profile, 'job_title', None) if profile else None
            return job_title

        served_by_user = getattr(transaction, 'created_by', None)
        fallback_user = request.user if request.user.is_authenticated else None
        served_by_name = resolve_user_name(served_by_user) or resolve_user_name(fallback_user) or 'Sales Team'
        served_by_role = resolve_job_title(served_by_user) or resolve_job_title(fallback_user) or 'Sales Clerk'

        return render(request, 'sales/receipt.html', {
            'transaction': transaction,
            'line_items': items,
            'subtotal': subtotal,
            'discount_amount': discount_amount,
            'tax_amount': tax_amount,
            'grand_total': transaction.total_amount,
            'served_by_name': served_by_name,
            'served_by_role': served_by_role,
        })


class SalesUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.change_salestransaction'

    def get(self, request, pk):
        transaction = get_object_or_404(SalesTransaction, pk=pk)
        form = SalesTransactionForm(instance=transaction)
        return render(request, 'sales/transaction_form.html', {
            'form': form,
            'transaction': transaction,
            'title': 'Edit Sale',
            'submit_label': 'Update Sale'
        })

    def post(self, request, pk):
        transaction = get_object_or_404(SalesTransaction, pk=pk)
        form = SalesTransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            form.save()
            messages.success(request, f"Sale {transaction.transaction_id} updated successfully.")
            return redirect('sales:dashboard')
        return render(request, 'sales/transaction_form.html', {
            'form': form,
            'transaction': transaction,
            'title': 'Edit Sale',
            'submit_label': 'Update Sale'
        })


class SalesDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.delete_salestransaction'

    def get(self, request, pk):
        transaction = get_object_or_404(SalesTransaction, pk=pk)
        return render(request, 'sales/transaction_confirm_delete.html', {'transaction': transaction})

    def post(self, request, pk):
        transaction = get_object_or_404(SalesTransaction, pk=pk)
        for line in transaction.items.select_related('inventory_item'):
            item = line.inventory_item
            item.current_quantity += line.quantity
            item.save(update_fields=['current_quantity'])
            adjust_storage_for_inventory_item(item, line.quantity)
        txn_id = transaction.transaction_id
        transaction.delete()
        messages.success(request, f"Sale {txn_id} deleted and stock restored.")
        return redirect('sales:dashboard')

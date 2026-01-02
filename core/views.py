import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.forms import AdminPasswordChangeForm, PasswordChangeForm
from django.contrib.auth.models import Group, Permission, User
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncMonth
from django.db.utils import OperationalError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from customers.models import Customer
from production.models import Cow, MilkYield
from sales.models import SalesItem, SalesTransaction
from storage.models import ColdStorageInventory, StorageLocation

from .forms import (
    GroupForm,
    GroupPermissionForm,
    UserCreateForm,
    UserGroupAssignmentForm,
    UserGroupInlineForm,
    UserProfileForm,
    UserSettingsForm,
    UserUpdateForm,
)
from .models import DataQualityAlert, UserProfile
from .services import run_data_quality_checks
from .roles import ROLE_CONFIG


@login_required
@permission_required('core.view_dashboard', login_url='core:next_access', raise_exception=False)
def home(request):
    metrics = _build_dashboard_metrics()

    if request.GET.get('export') == 'metrics':
        return _export_metrics_csv(metrics)

    return render(request, 'index.html', metrics)


LINE_TOTAL_FIELD = ExpressionWrapper(
    F('quantity') * F('price_per_unit'),
    output_field=DecimalField(max_digits=12, decimal_places=2),
)


def _build_dashboard_metrics():
    now = timezone.now()
    today = now.date()
    alerts = list(run_data_quality_checks())

    latest_yields = MilkYield.objects.select_related('cow')[:5]
    milk_today_total = MilkYield.objects.filter(recorded_at__date=today).aggregate(
        total=Sum('yield_litres')
    )['total'] or Decimal('0')
    active_herd_count = Cow.objects.filter(is_active=True).count()
    customers_today = Customer.objects.filter(created_at__date=today).count()

    yield_context = _build_yield_context(now)
    revenue_context = _build_revenue_context(now)
    profitability_context = _build_profitability_context(now)
    storage_context = _build_storage_context(now)
    top_products = _build_top_products()

    context = {
        'latest_yields': latest_yields,
        'milk_collected_today': milk_today_total,
        'active_herd_count': active_herd_count,
        'customers_today': customers_today,
        'today': today,
        'quality_alerts': alerts,
        'quality_alert_count': len(alerts),
        'top_products': top_products,
    }
    context.update(yield_context)
    context.update(revenue_context)
    context.update(profitability_context)
    context.update(storage_context)
    return context


def _build_yield_context(now):
    chart_year = now.year
    yield_qs = MilkYield.objects.filter(recorded_at__year=chart_year)
    if not yield_qs.exists():
        latest_year = (
            MilkYield.objects.order_by('-recorded_at')
            .values_list('recorded_at__year', flat=True)
            .first()
        )
        if latest_year:
            chart_year = latest_year
            yield_qs = MilkYield.objects.filter(recorded_at__year=chart_year)

    monthly_output_data = [0] * 12
    monthly_totals = (
        yield_qs
        .annotate(month=TruncMonth('recorded_at'))
        .values('month')
        .annotate(total=Sum('yield_litres'))
    )
    for entry in monthly_totals:
        month = entry['month']
        if month:
            month_index = month.month - 1
            monthly_output_data[month_index] = float(entry['total'] or 0)

    return {
        'monthly_output_data': monthly_output_data,
        'chart_year': chart_year,
    }


def _build_revenue_context(now):
    monthly_revenue = (
        SalesTransaction.objects
        .annotate(period=TruncMonth('created_at'))
        .values('period')
        .annotate(total=Sum('total_amount'))
        .order_by('period')
    )

    revenue_series = []
    recent_values = []
    for entry in monthly_revenue:
        period = entry['period']
        total = Decimal(entry['total'] or 0)
        if period:
            revenue_series.append({
                'label': period.strftime('%b %Y'),
                'value': float(total),
            })
            recent_values.append(total)

    recent_window = recent_values[-3:]
    forecast = sum(recent_window, Decimal('0')) / Decimal(len(recent_window)) if recent_window else Decimal('0')

    first_of_month = now.replace(day=1)
    previous_month_end = first_of_month - timedelta(days=1)

    revenue_this_month = SalesTransaction.objects.filter(
        created_at__year=now.year,
        created_at__month=now.month,
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    revenue_last_month = SalesTransaction.objects.filter(
        created_at__year=previous_month_end.year,
        created_at__month=previous_month_end.month,
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    return {
        'projected_revenue': revenue_this_month,
        'revenue_last_month': revenue_last_month,
        'forecast_next_month': forecast,
        'monthly_revenue_series': revenue_series[-6:],
    }


def _build_profitability_context(now):
    current_month_items = SalesItem.objects.select_related('inventory_item', 'transaction').filter(
        transaction__created_at__year=now.year,
        transaction__created_at__month=now.month,
    )

    revenue_this_month = Decimal('0')
    gross_profit = Decimal('0')

    for item in current_month_items:
        line_revenue = (item.quantity or Decimal('0')) * (item.price_per_unit or Decimal('0'))
        cost_basis = (item.quantity or Decimal('0')) * (item.inventory_item.default_price or Decimal('0'))
        revenue_this_month += line_revenue
        gross_profit += line_revenue - cost_basis

    gross_margin_pct = Decimal('0')
    if revenue_this_month > 0:
        gross_margin_pct = (gross_profit / revenue_this_month) * Decimal('100')

    return {
        'gross_profit': gross_profit,
        'gross_margin_pct': gross_margin_pct,
        'revenue_contribution': revenue_this_month,
    }


def _build_storage_context(now):
    total_capacity = StorageLocation.objects.aggregate(total=Sum('capacity'))['total'] or Decimal('0')
    total_on_hand = ColdStorageInventory.objects.aggregate(total=Sum('quantity'))['total'] or Decimal('0')

    if not isinstance(total_capacity, Decimal):
        total_capacity = Decimal(total_capacity)
    if not isinstance(total_on_hand, Decimal):
        total_on_hand = Decimal(total_on_hand)

    fill_pct = Decimal('0')
    if total_capacity > 0:
        fill_pct = (total_on_hand / total_capacity) * Decimal('100')
    chilling_capacity_pct = float(round(fill_pct, 1)) if fill_pct else 0

    expiring_cutoff = now.date() + timedelta(days=7)
    warning_threshold = now.date() + timedelta(days=2)
    expiring_qs = ColdStorageInventory.objects.select_related('location').filter(expiry_date__lte=expiring_cutoff)
    expiring_preview = list(expiring_qs.order_by('expiry_date')[:5])

    return {
        'chilling_capacity_pct': chilling_capacity_pct,
        'storage_lot_count': ColdStorageInventory.objects.count(),
        'storage_expiring_count': expiring_qs.count(),
        'storage_expiring_preview': expiring_preview,
        'storage_warning_threshold': warning_threshold,
    }


def _build_top_products():
    queryset = (
        SalesItem.objects
        .values('inventory_item__name', 'inventory_item__sku')
        .annotate(revenue=Sum(LINE_TOTAL_FIELD), quantity=Sum('quantity'))
        .order_by('-revenue')[:5]
    )
    data = []
    for entry in queryset:
        data.append({
            'name': entry['inventory_item__name'] or 'Unnamed',
            'sku': entry['inventory_item__sku'] or '—',
            'revenue': entry['revenue'] or Decimal('0'),
            'quantity': entry['quantity'] or Decimal('0'),
        })
    return data


def _export_metrics_csv(metrics):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="nawasons-metrics.csv"'
    writer = csv.writer(response)
    writer.writerow(['Metric', 'Value'])
    writer.writerow(['Milk Collected Today (L)', metrics['milk_collected_today']])
    writer.writerow(['Active Herd', metrics['active_herd_count']])
    writer.writerow(['Customers Added Today', metrics['customers_today']])
    writer.writerow(['Chilling Capacity %', metrics['chilling_capacity_pct']])
    writer.writerow(['Cold Storage Lots', metrics['storage_lot_count']])
    writer.writerow(['Expiring Cold Lots', metrics['storage_expiring_count']])
    writer.writerow(['Revenue This Month (KES)', metrics['projected_revenue']])
    writer.writerow(['Revenue Last Month (KES)', metrics['revenue_last_month']])
    writer.writerow(['Forecast Next Month (KES)', metrics['forecast_next_month']])
    writer.writerow(['Gross Profit (KES)', metrics['gross_profit']])
    writer.writerow(['Gross Margin %', metrics['gross_margin_pct']])
    writer.writerow(['Unresolved Alerts', metrics['quality_alert_count']])
    return response


def docs_chapter1(request):
    return render(request, 'docs/chapter1.html')


@login_required
def next_access(request):
    destination = _resolve_next_accessible_route(request.user)
    if destination:
        messages.info(request, 'You have been redirected to an area you can access.')
        return redirect(destination)
    messages.warning(request, 'No accessible sections were found. Update your permissions or contact an administrator.')
    return redirect('core:profile_settings')


@login_required
@permission_required('auth.view_user', raise_exception=True)
def user_management(request):
    user_form = UserCreateForm()
    group_form = GroupForm()
    permission_form = GroupPermissionForm()
    assignment_form = UserGroupAssignmentForm()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_user':
            user_form = UserCreateForm(request.POST)
            if user_form.is_valid():
                user_form.save()
                messages.success(request, 'User account created successfully.')
                return redirect('core:user_management')
            messages.error(request, 'Please correct the errors in the user form.')

        elif action == 'create_group':
            group_form = GroupForm(request.POST)
            if group_form.is_valid():
                group_form.save()
                messages.success(request, 'Group created successfully.')
                return redirect('core:user_management')
            messages.error(request, 'Unable to create the group. Please review the form.')

        elif action == 'update_group_permissions':
            permission_form = GroupPermissionForm(request.POST)
            if permission_form.is_valid():
                group = permission_form.cleaned_data['group']
                perms = permission_form.cleaned_data['permissions']
                group.permissions.set(perms)
                messages.success(request, f'Permissions updated for group "{group.name}".')
                return redirect('core:user_management')
            messages.error(request, 'Could not update permissions for the selected group.')

        elif action == 'assign_groups':
            assignment_form = UserGroupAssignmentForm(request.POST)
            if assignment_form.is_valid():
                assignment_form.save()
                messages.success(request, 'User groups updated successfully.')
                return redirect('core:user_management')
            messages.error(request, 'Unable to update user groups.')

        elif action == 'delete_user':
            user_id = request.POST.get('user_id')
            if str(request.user.pk) == user_id:
                messages.error(request, 'You cannot delete the account you are currently using.')
            else:
                User.objects.filter(pk=user_id).delete()
                messages.success(request, 'User removed.')
            return redirect('core:user_management')

        elif action == 'delete_group':
            group_id = request.POST.get('group_id')
            Group.objects.filter(pk=group_id).delete()
            messages.success(request, 'Group deleted.')
            return redirect('core:user_management')

    users = User.objects.select_related().order_by('username')
    groups = Group.objects.prefetch_related('permissions').order_by('name')
    permissions = Permission.objects.select_related('content_type').order_by('content_type__app_label', 'codename')

    context = {
        'user_form': user_form,
        'group_form': group_form,
        'permission_form': permission_form,
        'assignment_form': assignment_form,
        'users': users,
        'groups': groups,
        'permissions': permissions,
    }
    return render(request, 'core/user_management.html', context)


@login_required
@permission_required('auth.change_user', raise_exception=True)
def user_edit(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    user_form = UserUpdateForm(instance=user_obj)
    group_form = UserGroupInlineForm(initial={'groups': user_obj.groups.all()})
    password_form = AdminPasswordChangeForm(user_obj)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_user':
            user_form = UserUpdateForm(request.POST, instance=user_obj)
            if user_form.is_valid():
                user_form.save()
                messages.success(request, 'User details updated.')
                return redirect('core:user_edit', pk=pk)
            messages.error(request, 'Please fix the highlighted errors.')

        elif action == 'update_groups':
            group_form = UserGroupInlineForm(request.POST)
            if group_form.is_valid():
                user_obj.groups.set(group_form.cleaned_data['groups'])
                messages.success(request, 'Group membership updated.')
                return redirect('core:user_edit', pk=pk)
            messages.error(request, 'Unable to update group membership.')

        elif action == 'change_password':
            password_form = AdminPasswordChangeForm(user_obj, request.POST)
            if password_form.is_valid():
                password_form.save()
                if request.user.pk == user_obj.pk:
                    update_session_auth_hash(request, user_obj)
                messages.success(request, 'Password updated for the selected user.')
                return redirect('core:user_edit', pk=pk)
            messages.error(request, 'Password change failed. Please review the form.')

    context = {
        'managed_user': user_obj,
        'user_form': user_form,
        'group_form': group_form,
        'password_form': password_form,
    }
    return render(request, 'core/user_edit.html', context)


@login_required
def profile_settings(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    account_form = UserSettingsForm(instance=request.user)
    profile_form = UserProfileForm(instance=profile)
    password_form = PasswordChangeForm(request.user)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_account':
            account_form = UserSettingsForm(request.POST, instance=request.user)
            if account_form.is_valid():
                account_form.save()
                messages.success(request, 'Account details updated.')
                return redirect('core:profile_settings')
            messages.error(request, 'Please correct the errors below.')

        elif action == 'update_profile':
            profile_form = UserProfileForm(request.POST, request.FILES, instance=profile)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profile updated successfully.')
                return redirect('core:profile_settings')
            messages.error(request, 'Could not update your profile.')

        elif action == 'change_password':
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Password changed successfully.')
                return redirect('core:profile_settings')
            messages.error(request, 'Password change failed. Please review the form.')

    context = {
        'profile': profile,
        'account_form': account_form,
        'profile_form': profile_form,
        'password_form': password_form,
    }
    return render(request, 'core/profile_settings.html', context)


def seed_roles():
    try:
        for role_name, config in ROLE_CONFIG.items():
            group, _ = Group.objects.get_or_create(name=role_name)
            perms = Permission.objects.filter(codename__in=[perm.split('.')[-1] for perm in config['permissions']])
            group.permissions.set(perms)
    except OperationalError:
        pass

seed_roles()


FALLBACK_ROUTES = [
    ('customers.view_customer', 'customers:index'),
    ('sales.view_salestransaction', 'sales:dashboard'),
    ('inventory.view_inventoryitem', 'inventory:dashboard'),
    ('lab.view_batchtest', 'lab:dashboard'),
    ('production.view_productprice', 'production:price_list'),
    ('suppliers.view_supplier', 'suppliers:manage'),
    ('reports.view_reports_dashboard', 'reports:index'),
    ('auth.view_user', 'core:user_management'),
    (None, 'core:profile_settings'),
]


def _resolve_next_accessible_route(user):
    for perm, route in FALLBACK_ROUTES:
        if perm is None or user.has_perm(perm):
            if route == 'core:home' and not user.has_perm('core.view_dashboard'):
                continue
            return route
    return None

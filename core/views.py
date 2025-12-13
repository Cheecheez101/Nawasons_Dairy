from django.shortcuts import render
from production.models import MilkYield
from django.contrib.auth.models import Group, Permission
from django.db.utils import OperationalError
from .roles import ROLE_CONFIG


def home(request):
    latest_yields = MilkYield.objects.select_related('cow')[:5]
    context = {'latest_yields': latest_yields}
    return render(request, 'index.html', context)


def docs_chapter1(request):
    return render(request, 'docs/chapter1.html')


def seed_roles():
    try:
        for role_name, config in ROLE_CONFIG.items():
            group, _ = Group.objects.get_or_create(name=role_name)
            perms = Permission.objects.filter(codename__in=[perm.split('.')[-1] for perm in config['permissions']])
            group.permissions.set(perms)
    except OperationalError:
        pass

seed_roles()

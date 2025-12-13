from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from core.roles import ROLE_CONFIG

class Command(BaseCommand):
    help = 'Seed predefined user roles and permissions.'

    def handle(self, *args, **options):
        for role_name, config in ROLE_CONFIG.items():
            group, created = Group.objects.get_or_create(name=role_name)
            perms = Permission.objects.filter(codename__in=[perm.split('.')[-1] for perm in config['permissions']])
            group.permissions.set(perms)
            self.stdout.write(self.style.SUCCESS(f"Ensured group {role_name}"))


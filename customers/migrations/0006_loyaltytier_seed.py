from django.db import migrations


def seed_loyalty_tiers(apps, schema_editor):
    LoyaltyTier = apps.get_model('customers', 'LoyaltyTier')
    if LoyaltyTier.objects.exists():
        return
    tiers = [
        ('Starter', 0, 25, 5, '0-25 => 5 pts'),
        ('Bronze', 25, 50, 10, '25-50 => 10 pts'),
        ('Silver', 50, 100, 20, '50-100 => 20 pts'),
        ('Gold', 100, 250, 30, '100-250 => 30 pts'),
        ('Platinum', 250, 500, 50, '250-500 => 50 pts'),
        ('Diamond', 500, None, 80, '500+ => 80 pts'),
    ]
    for name, min_spend, max_spend, points, notes in tiers:
        LoyaltyTier.objects.create(
            name=name,
            min_spend=min_spend,
            max_spend=max_spend,
            points_awarded=points,
            notes=notes,
        )

def unseed_loyalty_tiers(apps, schema_editor):
    LoyaltyTier = apps.get_model('customers', 'LoyaltyTier')
    LoyaltyTier.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0005_loyaltytier'),
    ]

    operations = [
        migrations.RunPython(seed_loyalty_tiers, unseed_loyalty_tiers),
    ]


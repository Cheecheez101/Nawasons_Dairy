# Generated manually for changing milk_source to source_tank

from django.db import migrations, models


def migrate_data_forward(apps, schema_editor):
    ProductionBatch = apps.get_model('production', 'ProductionBatch')
    for batch in ProductionBatch.objects.all():
        batch.source_tank = batch.milk_source.storage_tank
        batch.save()


def migrate_data_reverse(apps, schema_editor):
    # Not reversible easily
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('production', '0006_milkyield_raw_test_approved_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='productionbatch',
            name='source_tank',
            field=models.CharField(choices=[('Unassigned', 'Unassigned'), ('Tank A', 'Tank A'), ('Tank B', 'Tank B'), ('Tank C', 'Tank C'), ('Spoilt Tank', 'Spoilt Tank')], default='Unassigned', max_length=40),
        ),
        migrations.RunPython(migrate_data_forward, migrate_data_reverse),
        migrations.RemoveField(
            model_name='productionbatch',
            name='milk_source',
        ),
    ]

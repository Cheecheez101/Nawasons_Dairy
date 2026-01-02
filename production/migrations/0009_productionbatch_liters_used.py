from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('production', '0008_alter_milkyield_storage_tank_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='productionbatch',
            name='liters_used',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]

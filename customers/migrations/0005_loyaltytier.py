from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0004_loyaltyledger'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoyaltyTier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('min_spend', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('max_spend', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(0)])),
                ('points_awarded', models.PositiveIntegerField()),
                ('notes', models.CharField(blank=True, max_length=255)),
            ],
            options={
                'ordering': ['min_spend'],
            },
        ),
    ]


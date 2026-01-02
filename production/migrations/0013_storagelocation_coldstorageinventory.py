from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("production", "0012_remove_milkyield_tank_test_latest_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="StorageLocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True)),
                ("capacity", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ColdStorageInventory",
            fields=[
                ("storage_id", models.AutoField(primary_key=True, serialize=False)),
                ("product", models.CharField(max_length=100)),
                ("expiry_date", models.DateField()),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=10)),
                ("status", models.CharField(choices=[("in_storage", "✅ In cold storage"), ("near_expiry", "⏳ Near expiry — prioritize dispatch"), ("expired", "❌ Expired — block dispatch")], default="in_storage", max_length=20)),
                ("last_restocked", models.DateTimeField(auto_now_add=True)),
                ("audit_notes", models.TextField(blank=True)),
                ("location", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory", to="production.storagelocation")),
                ("production_batch", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="storage_record", to="production.productionbatch")),
            ],
            options={
                "ordering": ["expiry_date"],
            },
        ),
    ]

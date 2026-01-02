from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("production", "0009_productionbatch_liters_used"),
    ]

    operations = [
        migrations.AddField(
            model_name="milkyield",
            name="collection_window_end",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="milkyield",
            name="collection_window_start",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="productionbatch",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending_lab", "Awaiting Lab"),
                    ("lab_approved", "Lab Approved"),
                    ("ready_for_store", "Ready for Storage"),
                ],
                default="pending_lab",
                max_length=20,
            ),
        ),
    ]

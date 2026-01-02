from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("lab", "0007_batch_closed_at_batch_closed_by_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CollectionWindowOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_key", models.CharField(choices=[("morning", "Morning"), ("afternoon", "Afternoon"), ("evening", "Evening")], max_length=20, unique=True)),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="collection_window_overrides", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "ordering": ["session_key"],
                "verbose_name": "Collection window override",
                "verbose_name_plural": "Collection window overrides",
            },
        ),
    ]

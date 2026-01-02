from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lab", "0008_collectionwindowoverride"),
    ]

    operations = [
        migrations.AddField(
            model_name="batch",
            name="auto_managed",
            field=models.BooleanField(
                default=True,
                help_text="If true, the system controls open/close transitions based on intake windows.",
            ),
        ),
    ]

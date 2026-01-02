from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("production", "0011_remove_milkyield_raw_test_approved"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="milkyield",
            name="tank_test_latest_status",
        ),
    ]

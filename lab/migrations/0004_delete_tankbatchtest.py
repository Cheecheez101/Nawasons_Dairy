from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("lab", "0003_delete_rawmilktest"),
    ]

    operations = [
        migrations.DeleteModel(
            name="TankBatchTest",
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0054_repair_misdated_lexware_sep_2026')]

    operations = [
        migrations.AddField(
            model_name='workingtimesetting',
            name='holiday_surcharge_percent',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=6),
        ),
    ]

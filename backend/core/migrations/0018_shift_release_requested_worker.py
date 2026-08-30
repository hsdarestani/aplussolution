import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_shift_color_hue'),
    ]

    operations = [
        migrations.AddField(
            model_name='shiftreleaserequest',
            name='requested_worker',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='requested_shift_releases',
                to='core.workerprofile',
            ),
        ),
    ]

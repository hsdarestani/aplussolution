from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0016_shift_release_request'),
    ]

    operations = [
        migrations.AddField(
            model_name='shift',
            name='color_hue',
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(359)],
            ),
        ),
    ]

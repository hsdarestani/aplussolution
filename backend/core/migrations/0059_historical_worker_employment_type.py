from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0058_review_extended_shift_times_october_2026')]

    operations = [
        migrations.AlterField(
            model_name='workerprofile',
            name='employment_type',
            field=models.CharField(
                max_length=20, default='minijob',
                choices=[
                    ('minijob', 'Minijob'),
                    ('teilzeit', 'Teilzeit'),
                    ('vollzeit', 'Vollzeit'),
                    ('student', 'Studentische Aushilfe'),
                    ('historisch', 'Historische Akte (Lohnart unbekannt)'),
                ],
            ),
        ),
    ]

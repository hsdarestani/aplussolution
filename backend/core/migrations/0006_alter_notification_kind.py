from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0005_timeentrycorrection')]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='kind',
            field=models.CharField(default='general', max_length=120),
        ),
    ]

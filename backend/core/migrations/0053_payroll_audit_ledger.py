from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0052_shift_plan_attachment_visibility'),
    ]

    operations = [
        migrations.AddField(
            model_name='workingtimeaccountrecord',
            name='paid_total_hours',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='workingtimesetting',
            name='night_surcharge_percent',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=6),
        ),
        migrations.AddField(
            model_name='workingtimesetting',
            name='saturday_surcharge_percent',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=6),
        ),
        migrations.AddField(
            model_name='workingtimesetting',
            name='sunday_surcharge_percent',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=6),
        ),
        migrations.AddField(
            model_name='payrollstatement',
            name='transferred_amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='payrollstatement',
            name='payment_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='payrollstatement',
            name='source',
            field=models.CharField(default='manual', max_length=40),
        ),
        migrations.AddField(
            model_name='payrollstatement',
            name='source_reference',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='payrollstatement',
            name='raw_data',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name='payrollstatement',
            name='document',
            field=models.FileField(blank=True, null=True, upload_to='payroll/%Y/%m/'),
        ),
    ]

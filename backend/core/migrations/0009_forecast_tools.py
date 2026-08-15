import uuid

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0008_scheduler_parity')]

    operations = [
        migrations.CreateModel(
            name='ForecastDayBudget',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('date', models.DateField()),
                ('sales_budget', models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[django.core.validators.MinValueValidator(0)])),
                ('actual_sales', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True, validators=[django.core.validators.MinValueValidator(0)])),
                ('labor_percent_target', models.DecimalField(decimal_places=2, default=0, max_digits=6, validators=[django.core.validators.MinValueValidator(0)])),
                ('hours_budget', models.DecimalField(decimal_places=2, default=0, max_digits=9, validators=[django.core.validators.MinValueValidator(0)])),
                ('schedule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='forecast_days', to='core.schedulegroup')),
            ],
            options={'ordering': ['date'], 'unique_together': {('schedule', 'date')}},
        ),
        migrations.CreateModel(
            name='ForecastUnitDefinition',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=140)),
                ('unit_label', models.CharField(default='Einheiten', max_length=80)),
                ('mode', models.CharField(choices=[('shifts', 'Schichten je Position'), ('hours', 'Stunden je Position')], default='hours', max_length=20)),
                ('active', models.BooleanField(default=True)),
                ('schedule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='forecast_units', to='core.schedulegroup')),
            ],
            options={'ordering': ['schedule__name', 'name'], 'unique_together': {('schedule', 'name')}},
        ),
        migrations.CreateModel(
            name='ForecastPositionRequirement',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('units_basis', models.DecimalField(decimal_places=2, default=1, max_digits=12, validators=[django.core.validators.MinValueValidator(0.01)])),
                ('required_value', models.DecimalField(decimal_places=2, default=1, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ('definition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='requirements', to='core.forecastunitdefinition')),
                ('position', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='forecast_requirements', to='core.position')),
            ],
            options={'ordering': ['position__name'], 'unique_together': {('definition', 'position')}},
        ),
        migrations.CreateModel(
            name='ForecastUnitDay',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('date', models.DateField()),
                ('projected_units', models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[django.core.validators.MinValueValidator(0)])),
                ('actual_units', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True, validators=[django.core.validators.MinValueValidator(0)])),
                ('definition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='days', to='core.forecastunitdefinition')),
            ],
            options={'ordering': ['date'], 'unique_together': {('definition', 'date')}},
        ),
    ]

from django.core.validators import MinValueValidator
from django.db import models

from .models import Position, TimestampedModel
from .scheduling_models import ScheduleGroup


class ForecastDayBudget(TimestampedModel):
    schedule = models.ForeignKey(ScheduleGroup, on_delete=models.CASCADE, related_name='forecast_days')
    date = models.DateField()
    sales_budget = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    actual_sales = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0)])
    labor_percent_target = models.DecimalField(max_digits=6, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    hours_budget = models.DecimalField(max_digits=9, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    class Meta:
        app_label = 'core'
        unique_together = ('schedule', 'date')
        ordering = ['date']


class ForecastUnitDefinition(TimestampedModel):
    class Mode(models.TextChoices):
        SHIFTS = 'shifts', 'Schichten je Position'
        HOURS = 'hours', 'Stunden je Position'

    schedule = models.ForeignKey(ScheduleGroup, on_delete=models.CASCADE, related_name='forecast_units')
    name = models.CharField(max_length=140)
    unit_label = models.CharField(max_length=80, default='Einheiten')
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.HOURS)
    active = models.BooleanField(default=True)

    class Meta:
        app_label = 'core'
        unique_together = ('schedule', 'name')
        ordering = ['schedule__name', 'name']

    def __str__(self):
        return f'{self.schedule.name} · {self.name}'


class ForecastPositionRequirement(TimestampedModel):
    definition = models.ForeignKey(ForecastUnitDefinition, on_delete=models.CASCADE, related_name='requirements')
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='forecast_requirements')
    units_basis = models.DecimalField(max_digits=12, decimal_places=2, default=1, validators=[MinValueValidator(0.01)])
    required_value = models.DecimalField(max_digits=10, decimal_places=2, default=1, validators=[MinValueValidator(0)])

    class Meta:
        app_label = 'core'
        unique_together = ('definition', 'position')
        ordering = ['position__name']


class ForecastUnitDay(TimestampedModel):
    definition = models.ForeignKey(ForecastUnitDefinition, on_delete=models.CASCADE, related_name='days')
    date = models.DateField()
    projected_units = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    actual_units = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0)])

    class Meta:
        app_label = 'core'
        unique_together = ('definition', 'date')
        ordering = ['date']

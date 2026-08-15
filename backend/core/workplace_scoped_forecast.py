import csv
import json
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from . import forecast_views
from .forecast_models import ForecastDayBudget, ForecastUnitDay, ForecastUnitDefinition
from .permissions import IsAdminOrManager
from .services import audit
from .shift_slots import ShiftSlot
from .workplace_access import can_view_wage, has_capability, visible_schedule_groups


def _require(user, capability):
    if not has_capability(user, capability):
        raise PermissionDenied('Keine Berechtigung für diese Funktion.')


def _schedule_allowed(user, schedule):
    return visible_schedule_groups(user).filter(pk=schedule.pk).exists()


def _guard_schedule(user, schedule, capability='schedule.view'):
    _require(user, capability)
    if not _schedule_allowed(user, schedule):
        raise PermissionDenied('Dienstplan liegt außerhalb deines Verantwortungsbereichs.')


class ScopedForecastMixin:
    def get_permissions(self):
        self.required_capability = 'schedule.view' if getattr(self, 'action', None) in {'list', 'retrieve'} else 'schedule.edit'
        return [IsAdminOrManager()]


class ScopedForecastDayBudgetViewSet(ScopedForecastMixin, forecast_views.ForecastDayBudgetViewSet):
    def get_queryset(self):
        return self.queryset.filter(schedule__in=visible_schedule_groups(self.request.user)).distinct()

    def _guard(self, serializer):
        schedule = serializer.validated_data.get('schedule', getattr(serializer.instance, 'schedule', None))
        _guard_schedule(self.request.user, schedule, 'schedule.edit')

    def perform_create(self, serializer):
        self._guard(serializer)
        return super().perform_create(serializer)

    def perform_update(self, serializer):
        self._guard(serializer)
        return super().perform_update(serializer)


class ScopedForecastUnitDefinitionViewSet(ScopedForecastMixin, forecast_views.ForecastUnitDefinitionViewSet):
    def get_queryset(self):
        return self.queryset.filter(schedule__in=visible_schedule_groups(self.request.user)).distinct()

    def _guard(self, serializer):
        schedule = serializer.validated_data.get('schedule', getattr(serializer.instance, 'schedule', None))
        _guard_schedule(self.request.user, schedule, 'schedule.edit')

    def perform_create(self, serializer):
        self._guard(serializer)
        return super().perform_create(serializer)

    def perform_update(self, serializer):
        self._guard(serializer)
        return super().perform_update(serializer)


class ScopedForecastUnitDayViewSet(ScopedForecastMixin, forecast_views.ForecastUnitDayViewSet):
    def get_queryset(self):
        return self.queryset.filter(definition__schedule__in=visible_schedule_groups(self.request.user)).distinct()

    def _guard(self, serializer):
        definition = serializer.validated_data.get('definition', getattr(serializer.instance, 'definition', None))
        if not definition:
            raise PermissionDenied('Forecast-Einheit fehlt.')
        _guard_schedule(self.request.user, definition.schedule, 'schedule.edit')

    def perform_create(self, serializer):
        self._guard(serializer)
        return super().perform_create(serializer)

    def perform_update(self, serializer):
        self._guard(serializer)
        return super().perform_update(serializer)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def forecast_summary(request):
    from .scheduling_models import ScheduleGroup

    schedule = ScheduleGroup.objects.prefetch_related('locations').filter(pk=request.GET.get('schedule'), active=True).first()
    if not schedule:
        return Response({'detail': 'Gültiger Dienstplan ist erforderlich.'}, status=400)
    try:
        _guard_schedule(request.user, schedule, 'schedule.view')
    except PermissionDenied as exc:
        return Response({'detail': str(exc.detail)}, status=403)

    start = parse_date(str(request.GET.get('start') or '')) or timezone.localdate()
    end = parse_date(str(request.GET.get('end') or '')) or (start + timedelta(days=7))
    if end <= start or (end - start).days > 92:
        return Response({'detail': 'Forecast-Zeitraum muss zwischen 1 und 92 Tagen liegen.'}, status=400)

    shifts = list(forecast_views._schedule_shifts(schedule, start, end))
    budgets = {row.date: row for row in ForecastDayBudget.objects.filter(schedule=schedule, date__gte=start, date__lt=end)}
    definitions = list(ForecastUnitDefinition.objects.filter(schedule=schedule, active=True).prefetch_related('requirements__position', 'days'))
    unit_days = {(row.definition_id, row.date): row for row in ForecastUnitDay.objects.filter(definition__in=definitions, date__gte=start, date__lt=end)}
    days = []
    cursor = start
    while cursor < end:
        day_start, day_end = forecast_views._aware(cursor), forecast_views._aware(cursor + timedelta(days=1))
        day_shifts = [s for s in shifts if s.starts_at < day_end and s.ends_at > day_start]
        combined_minutes = 0
        assigned_minutes = 0
        labor_cost = Decimal('0')
        wage_complete = True
        position_stats = {}
        for shift in day_shifts:
            minutes = forecast_views._overlap_net_minutes(shift, day_start, day_end)
            if not minutes:
                continue
            demand = max(1, int(shift.required_count or 1))
            combined_minutes += minutes * demand
            claimed = [slot for slot in shift.slots.all() if slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id]
            assigned_minutes += minutes * len(claimed)
            stat = position_stats.setdefault(str(shift.position_id), {
                'position': str(shift.position_id), 'position_name': shift.position.name,
                'scheduled_shifts': 0, 'scheduled_hours': Decimal('0'),
            })
            stat['scheduled_shifts'] += demand
            stat['scheduled_hours'] += (Decimal(minutes) / Decimal(60)) * demand
            for slot in claimed:
                if not can_view_wage(request.user, slot.worker):
                    wage_complete = False
                    continue
                rate = Decimal(slot.worker.tariff_hourly_rate or 0) + Decimal(slot.worker.extra_allowance or 0)
                labor_cost += (Decimal(minutes) / Decimal(60)) * rate

        budget = budgets.get(cursor)
        sales = Decimal((budget.actual_sales if cursor < timezone.localdate() and budget and budget.actual_sales is not None else budget.sales_budget) if budget else 0)
        labor_target = Decimal(budget.labor_percent_target if budget else 0)
        hours_budget = Decimal(budget.hours_budget if budget else 0)
        labor_budget = sales * labor_target / Decimal(100) if labor_target else Decimal(0)
        assigned_percent = (labor_cost / sales * Decimal(100)) if sales and wage_complete else None
        custom = []
        for definition in definitions:
            unit_day = unit_days.get((definition.id, cursor))
            projected = Decimal(unit_day.actual_units if cursor < timezone.localdate() and unit_day and unit_day.actual_units is not None else unit_day.projected_units if unit_day else 0)
            requirements = []
            for requirement in definition.requirements.all():
                raw_required = projected / Decimal(requirement.units_basis) * Decimal(requirement.required_value) if requirement.units_basis else Decimal(0)
                required = raw_required.quantize(Decimal('1'), rounding=ROUND_CEILING) if definition.mode == ForecastUnitDefinition.Mode.SHIFTS else raw_required.quantize(Decimal('0.01'))
                stat = position_stats.get(str(requirement.position_id), {'scheduled_shifts': 0, 'scheduled_hours': Decimal(0)})
                scheduled = Decimal(stat['scheduled_shifts']) if definition.mode == ForecastUnitDefinition.Mode.SHIFTS else Decimal(stat['scheduled_hours'])
                requirements.append({
                    'position': str(requirement.position_id), 'position_name': requirement.position.name,
                    'required': str(required), 'scheduled': str(scheduled.quantize(Decimal('0.01'))),
                    'variance': str((scheduled-required).quantize(Decimal('0.01'))),
                })
            custom.append({
                'definition': str(definition.id), 'name': definition.name, 'unit_label': definition.unit_label,
                'mode': definition.mode, 'projected_units': str(projected), 'requirements': requirements,
            })

        combined_hours = Decimal(combined_minutes) / Decimal(60)
        assigned_hours = Decimal(assigned_minutes) / Decimal(60)
        days.append({
            'date': cursor.isoformat(),
            'sales_budget': forecast_views._money(sales),
            'labor_percent_target': forecast_views._money(labor_target),
            'labor_budget': forecast_views._money(labor_budget),
            'assigned_labor_cost': forecast_views._money(labor_cost) if wage_complete else None,
            'assigned_labor_percent': forecast_views._money(assigned_percent) if assigned_percent is not None else None,
            'labor_variance': forecast_views._money(labor_budget-labor_cost) if wage_complete else None,
            'wage_visibility_complete': wage_complete,
            'hours_budget': forecast_views._money(hours_budget),
            'combined_hours': forecast_views._money(combined_hours),
            'assigned_hours': forecast_views._money(assigned_hours),
            'hours_variance': forecast_views._money(hours_budget-combined_hours),
            'custom_units': custom,
        })
        cursor += timedelta(days=1)
    return Response({'schedule': str(schedule.id), 'schedule_name': schedule.name, 'start': start, 'end': end, 'days': days})


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def budget_upsert(request):
    from .scheduling_models import ScheduleGroup

    schedule = ScheduleGroup.objects.filter(pk=request.data.get('schedule'), active=True).first()
    day = parse_date(str(request.data.get('date') or ''))
    if not schedule or not day:
        return Response({'detail': 'Dienstplan und Datum sind erforderlich.'}, status=400)
    try:
        _guard_schedule(request.user, schedule, 'schedule.edit')
    except PermissionDenied as exc:
        return Response({'detail': str(exc.detail)}, status=403)
    values = {}
    for field in ('sales_budget', 'actual_sales', 'labor_percent_target', 'hours_budget'):
        if field in request.data:
            values[field] = request.data.get(field) if request.data.get(field) not in ('', None) else (None if field == 'actual_sales' else 0)
    obj, created = ForecastDayBudget.objects.update_or_create(schedule=schedule, date=day, defaults=values)
    audit(request, 'forecast.budget_upserted', obj, {'created': created})
    return Response(forecast_views.ForecastDayBudgetSerializer(obj).data, status=201 if created else 200)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def unit_day_upsert(request):
    definition = ForecastUnitDefinition.objects.select_related('schedule').filter(pk=request.data.get('definition'), active=True).first()
    day = parse_date(str(request.data.get('date') or ''))
    if not definition or not day:
        return Response({'detail': 'Forecast-Einheit und Datum sind erforderlich.'}, status=400)
    try:
        _guard_schedule(request.user, definition.schedule, 'schedule.edit')
    except PermissionDenied as exc:
        return Response({'detail': str(exc.detail)}, status=403)
    values = {}
    if 'projected_units' in request.data:
        values['projected_units'] = request.data.get('projected_units') or 0
    if 'actual_units' in request.data:
        values['actual_units'] = request.data.get('actual_units') if request.data.get('actual_units') not in ('', None) else None
    obj, created = ForecastUnitDay.objects.update_or_create(definition=definition, date=day, defaults=values)
    audit(request, 'forecast.unit_day_upserted', obj, {'created': created})
    return Response(forecast_views.ForecastUnitDaySerializer(obj).data, status=201 if created else 200)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def forecast_import_apply(request):
    from .scheduling_models import ScheduleGroup

    upload = request.FILES.get('file')
    schedule = ScheduleGroup.objects.filter(pk=request.data.get('schedule'), active=True).first()
    if not upload or not schedule:
        return Response({'detail': 'Forecast-Datei und Dienstplan sind erforderlich.'}, status=400)
    try:
        _guard_schedule(request.user, schedule, 'schedule.edit')
    except PermissionDenied as exc:
        return Response({'detail': str(exc.detail)}, status=403)
    try:
        mapping = json.loads(request.data.get('mapping') or '{}') if isinstance(request.data.get('mapping'), str) else (request.data.get('mapping') or {})
        rows = forecast_views._read_upload(upload)
    except (ValueError, UnicodeDecodeError, csv.Error, json.JSONDecodeError) as exc:
        return Response({'detail': str(exc)}, status=400)
    date_column = mapping.get('date')
    if not date_column:
        return Response({'detail': 'Datums-Spalte muss zugeordnet werden.'}, status=400)
    created = updated = 0
    errors = []
    unit_targets = {key.split(':', 1)[1]: source for key, source in mapping.items() if key.startswith('unit:') and source}
    definitions = {str(item.id): item for item in ForecastUnitDefinition.objects.filter(schedule=schedule, active=True)}
    for index, row in enumerate(rows, start=2):
        try:
            raw_date = row.get(date_column)
            if isinstance(raw_date, datetime):
                day = raw_date.date()
            else:
                day = parse_date(str(raw_date).strip())
                if not day:
                    for fmt in ('%d.%m.%Y', '%m/%d/%Y', '%d/%m/%Y'):
                        try:
                            day = datetime.strptime(str(raw_date).strip(), fmt).date()
                            break
                        except ValueError:
                            continue
            if not day:
                raise ValueError('Ungültiges Datum')
            defaults = {
                'sales_budget': forecast_views._decimal(row.get(mapping.get('sales_budget'))) if mapping.get('sales_budget') else 0,
                'hours_budget': forecast_views._decimal(row.get(mapping.get('hours_budget'))) if mapping.get('hours_budget') else 0,
                'labor_percent_target': forecast_views._decimal(row.get(mapping.get('labor_percent_target'))) if mapping.get('labor_percent_target') else 0,
            }
            if mapping.get('actual_sales'):
                value = row.get(mapping['actual_sales'])
                defaults['actual_sales'] = forecast_views._decimal(value) if value not in (None, '') else None
            _, was_created = ForecastDayBudget.objects.update_or_create(schedule=schedule, date=day, defaults=defaults)
            created += int(was_created)
            updated += int(not was_created)
            for definition_id, source_column in unit_targets.items():
                definition = definitions.get(definition_id)
                if definition:
                    ForecastUnitDay.objects.update_or_create(
                        definition=definition, date=day,
                        defaults={'projected_units': forecast_views._decimal(row.get(source_column))},
                    )
        except Exception as exc:
            errors.append({'line': index, 'error': str(exc)})
    audit(request, 'forecast.imported', schedule, {'created': created, 'updated': updated, 'errors': len(errors)})
    return Response({'created': created, 'updated': updated, 'errors': errors})

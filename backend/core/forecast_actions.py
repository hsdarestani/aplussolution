from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .forecast_models import ForecastDayBudget, ForecastUnitDay, ForecastUnitDefinition
from .forecast_views import ForecastDayBudgetSerializer, ForecastUnitDaySerializer
from .permissions import IsAdminOrManager
from .scheduling_models import ScheduleGroup
from .services import audit


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def budget_upsert(request):
    schedule = ScheduleGroup.objects.filter(pk=request.data.get('schedule'), active=True).first()
    day = parse_date(str(request.data.get('date') or ''))
    if not schedule or not day:
        return Response({'detail': 'Dienstplan und Datum sind erforderlich.'}, status=400)
    values = {}
    for field in ('sales_budget', 'actual_sales', 'labor_percent_target', 'hours_budget'):
        if field in request.data:
            values[field] = request.data.get(field) if request.data.get(field) not in ('', None) else (None if field == 'actual_sales' else 0)
    obj, created = ForecastDayBudget.objects.update_or_create(schedule=schedule, date=day, defaults=values)
    audit(request, 'forecast.budget_upserted', obj, {'created': created})
    return Response(ForecastDayBudgetSerializer(obj).data, status=201 if created else 200)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def unit_day_upsert(request):
    definition = ForecastUnitDefinition.objects.filter(pk=request.data.get('definition'), active=True).first()
    day = parse_date(str(request.data.get('date') or ''))
    if not definition or not day:
        return Response({'detail': 'Forecast-Einheit und Datum sind erforderlich.'}, status=400)
    values = {}
    if 'projected_units' in request.data:
        values['projected_units'] = request.data.get('projected_units') or 0
    if 'actual_units' in request.data:
        values['actual_units'] = request.data.get('actual_units') if request.data.get('actual_units') not in ('', None) else None
    obj, created = ForecastUnitDay.objects.update_or_create(definition=definition, date=day, defaults=values)
    audit(request, 'forecast.unit_day_upserted', obj, {'created': created})
    return Response(ForecastUnitDaySerializer(obj).data, status=201 if created else 200)

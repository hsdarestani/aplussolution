import csv
import hashlib
import hmac
import io
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal

import requests
from django.db import transaction
from django.utils import timezone

from .models import AuditLog, Availability, Shift, TimeEntry, TimeOffRequest, WorkerProfile
from .premium_approval_models import WorkerLocationMembership
from .premium_models import DailyForecast, SchedulingPolicy, WebhookDelivery, WebhookSubscription
from .shift_slots import ShiftSlot


def get_policy():
    return SchedulingPolicy.objects.filter(active=True).first() or SchedulingPolicy.objects.create(name='Standard')


def hours(shift):
    gross = Decimal(str((shift.ends_at - shift.starts_at).total_seconds() / 3600))
    return max(Decimal('0'), gross - Decimal(str(shift.break_minutes or 0)) / Decimal('60'))


def _consecutive_day_count(days):
    days = sorted(set(days))
    if not days:
        return 0
    longest = current = 1
    for previous, current_day in zip(days, days[1:]):
        if (current_day - previous).days == 1:
            current += 1
        else:
            current = 1
        longest = max(longest, current)
    return longest


def violations(worker, shift, policy=None):
    p = policy or get_policy()
    out = []
    required = set(shift.position.required_skills or [])
    if required and not required.issubset(set(worker.skills or [])):
        out.append('required_skills')
    if Availability.objects.filter(worker=worker, available=False, starts_at__lt=shift.ends_at, ends_at__gt=shift.starts_at).exists():
        out.append('unavailable')
    if TimeOffRequest.objects.filter(worker=worker, status=TimeOffRequest.Status.APPROVED, starts_on__lte=shift.ends_at.date(), ends_on__gte=shift.starts_at.date()).exists():
        out.append('approved_time_off')

    slots = list(ShiftSlot.objects.select_related('shift').filter(worker=worker, status=ShiftSlot.Status.CLAIMED).exclude(shift=shift))
    if any(s.shift.starts_at < shift.ends_at and s.shift.ends_at > shift.starts_at for s in slots):
        out.append('overlap')

    same_day = [s for s in slots if s.shift.starts_at.date() == shift.starts_at.date()]
    if same_day and not p.allow_multiple_shifts_per_day:
        out.append('multiple_shifts_per_day')

    for slot in slots:
        other = slot.shift
        if other.ends_at <= shift.starts_at:
            gap = Decimal(str((shift.starts_at - other.ends_at).total_seconds() / 3600))
            required_rest = p.min_hours_same_day if other.ends_at.date() == shift.starts_at.date() else p.min_hours_between_days
            if gap < required_rest:
                out.append('minimum_rest')
                break
        if shift.ends_at <= other.starts_at:
            gap = Decimal(str((other.starts_at - shift.ends_at).total_seconds() / 3600))
            required_rest = p.min_hours_same_day if shift.ends_at.date() == other.starts_at.date() else p.min_hours_between_days
            if gap < required_rest:
                out.append('minimum_rest')
                break

    if hours(shift) + sum((hours(s.shift) for s in same_day), Decimal('0')) > p.max_hours_per_day:
        out.append('max_hours_per_day')

    week_start = (shift.starts_at - timedelta(days=shift.starts_at.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)
    week = [s for s in slots if week_start <= s.shift.starts_at < week_end]
    if hours(shift) + sum((hours(s.shift) for s in week), Decimal('0')) > p.max_hours_per_week:
        out.append('max_hours_per_week')
    if len({shift.starts_at.date(), *[s.shift.starts_at.date() for s in week]}) > p.max_days_per_week:
        out.append('max_days_per_week')

    all_days = [shift.starts_at.date(), *[s.shift.starts_at.date() for s in slots]]
    if _consecutive_day_count(all_days) > p.max_days_in_row:
        out.append('max_days_in_row')

    if p.respect_worker_monthly_hours and worker.monthly_hours:
        month_start = shift.starts_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = month_start.replace(year=month_start.year + 1, month=1) if month_start.month == 12 else month_start.replace(month=month_start.month + 1)
        month = [s for s in slots if month_start <= s.shift.starts_at < month_end]
        if hours(shift) + sum((hours(s.shift) for s in month), Decimal('0')) > worker.monthly_hours:
            out.append('monthly_hours')
    return sorted(set(out))


def _workers_for_location(workers, location_id, policy):
    if policy.labor_sharing_enabled:
        return list(workers)
    memberships = WorkerLocationMembership.objects.filter(location_id=location_id, active=True).values_list('worker_id', flat=True)
    return [worker for worker in workers if worker.id in set(memberships)]


def auto_schedule(start, end, apply=False, location_id=None, worker_ids=None):
    policy = get_policy()
    if not policy.auto_schedule_enabled:
        raise ValueError('Auto Scheduling ist deaktiviert.')
    slots_qs = ShiftSlot.objects.select_related('shift__position', 'shift__location').filter(
        status=ShiftSlot.Status.OPEN,
        shift__starts_at__gte=start,
        shift__starts_at__lt=end,
        shift__status__in=[Shift.Status.DRAFT, Shift.Status.PUBLISHED],
    )
    if location_id:
        slots_qs = slots_qs.filter(shift__location_id=location_id)
    slots = list(slots_qs)
    slots.sort(key=lambda s: (0 if policy.weekend_first and s.shift.starts_at.weekday() >= 5 else 1, s.shift.starts_at))

    workers_qs = WorkerProfile.objects.select_related('user').filter(active=True, user__is_active=True)
    if worker_ids:
        workers_qs = workers_qs.filter(id__in=worker_ids)
    all_workers = list(workers_qs)
    rows = []
    with transaction.atomic():
        for slot in slots:
            candidates = []
            for worker in _workers_for_location(all_workers, slot.shift.location_id, policy):
                if violations(worker, slot.shift, policy):
                    continue
                load = sum((hours(x.shift) for x in ShiftSlot.objects.select_related('shift').filter(
                    worker=worker, status=ShiftSlot.Status.CLAIMED,
                    shift__starts_at__gte=start, shift__starts_at__lt=end,
                )), Decimal('0'))
                preferred = Availability.objects.filter(
                    worker=worker, available=True,
                    starts_at__lte=slot.shift.starts_at, ends_at__gte=slot.shift.ends_at,
                ).exists()
                candidates.append((load - (Decimal('2') if preferred else Decimal('0')), worker.user.email, worker))
            candidates.sort(key=lambda item: (item[0], item[1]))
            chosen = candidates[0][2] if candidates else None
            rows.append({
                'slot_id': str(slot.id), 'shift_id': str(slot.shift_id),
                'worker_id': str(chosen.id) if chosen else None,
                'worker': (chosen.user.get_full_name() or chosen.user.email) if chosen else None,
                'candidate_count': len(candidates),
            })
            if apply and chosen:
                slot.worker = chosen
                slot.status = ShiftSlot.Status.CLAIMED
                slot.source = 'auto'
                slot.claimed_at = timezone.now()
                slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])
    return {
        'apply': apply,
        'assigned': sum(bool(row['worker_id']) for row in rows),
        'unfilled': sum(not row['worker_id'] for row in rows),
        'results': rows,
    }


def labor_forecast(start, end, location_id=None):
    qs = DailyForecast.objects.select_related('location', 'metric').filter(date__gte=start, date__lte=end)
    if location_id:
        qs = qs.filter(location_id=location_id)
    rows = []
    for forecast in qs:
        day_start = timezone.make_aware(datetime.combine(forecast.date, datetime.min.time()))
        day_end = day_start + timedelta(days=1)
        total_hours = Decimal('0')
        labor_cost = Decimal('0')
        for slot in ShiftSlot.objects.select_related('shift', 'worker').filter(
            status=ShiftSlot.Status.CLAIMED, shift__location=forecast.location,
            shift__starts_at__lt=day_end, shift__ends_at__gt=day_start,
        ):
            shift_hours = hours(slot.shift)
            rate = (slot.worker.tariff_hourly_rate or 0) + (slot.worker.extra_allowance or 0)
            total_hours += shift_hours
            labor_cost += shift_hours * rate
        budget = forecast.labor_budget_amount or (
            forecast.projected_sales * forecast.labor_budget_percent / 100
            if forecast.projected_sales and forecast.labor_budget_percent else 0
        )
        rows.append({
            'id': str(forecast.id), 'date': forecast.date.isoformat(), 'location': forecast.location.name,
            'metric': forecast.metric.name if forecast.metric else None,
            'projected_units': str(forecast.projected_units), 'projected_sales': str(forecast.projected_sales),
            'scheduled_hours': str(total_hours), 'scheduled_labor_cost': str(labor_cost),
            'labor_budget': str(budget), 'variance': str(Decimal(budget) - labor_cost),
        })
    return rows


def _apply_report_filters(rows, filters):
    filters = filters or {}
    for key, expected in filters.items():
        if key in {'location_id'} or expected in {None, '', []}:
            continue
        if isinstance(expected, list):
            rows = [row for row in rows if row.get(key) in expected]
        else:
            expected_text = str(expected).lower()
            rows = [row for row in rows if expected_text in str(row.get(key, '')).lower()]
    return rows


def _apply_report_sorting(rows, sorting):
    for item in reversed(sorting or []):
        field = item.get('field') if isinstance(item, dict) else str(item).lstrip('-')
        descending = item.get('direction') == 'desc' if isinstance(item, dict) else str(item).startswith('-')
        rows.sort(key=lambda row: (row.get(field) is None, str(row.get(field, ''))), reverse=descending)
    return rows


def run_report(defn, start, end):
    rows = []
    if defn.kind == 'shifts':
        for shift in Shift.objects.select_related('location', 'position').filter(starts_at__gte=start, starts_at__lte=end):
            rows.append({'shift_id': str(shift.id), 'start': shift.starts_at.isoformat(), 'end': shift.ends_at.isoformat(), 'location': shift.location.name, 'position': shift.position.name, 'status': shift.status, 'required_count': shift.required_count, 'claimed_count': shift.slots.filter(status=ShiftSlot.Status.CLAIMED).count()})
    elif defn.kind == 'times':
        for entry in TimeEntry.objects.select_related('worker__user', 'shift__location').filter(clock_in__gte=start, clock_in__lte=end):
            rows.append({'time_id': str(entry.id), 'worker': entry.worker.user.get_full_name() or entry.worker.user.email, 'employee_number': entry.worker.employee_number, 'clock_in': entry.clock_in.isoformat(), 'clock_out': entry.clock_out.isoformat() if entry.clock_out else None, 'worked_minutes': entry.worked_minutes, 'approved': entry.approved, 'location': entry.shift.location.name if entry.shift else None})
    elif defn.kind == 'shift_history':
        for log in AuditLog.objects.select_related('actor').filter(created_at__gte=start, created_at__lte=end, object_type__icontains='shift'):
            rows.append({'timestamp': log.created_at.isoformat(), 'actor': log.actor.email if log.actor else None, 'action': log.action, 'shift_id': log.object_id, 'metadata': log.metadata})
    elif defn.kind == 'users':
        for worker in WorkerProfile.objects.select_related('user'):
            rows.append({'worker_id': str(worker.id), 'employee_number': worker.employee_number, 'name': worker.user.get_full_name(), 'email': worker.user.email, 'employment_type': worker.employment_type, 'monthly_hours': str(worker.monthly_hours or ''), 'skills': worker.skills, 'active': worker.active})
    elif defn.kind == 'time_off':
        for request in TimeOffRequest.objects.select_related('worker__user').filter(starts_on__lte=end.date(), ends_on__gte=start.date()):
            rows.append({'request_id': str(request.id), 'worker': request.worker.user.get_full_name() or request.worker.user.email, 'start': request.starts_on.isoformat(), 'end': request.ends_on.isoformat(), 'status': request.status, 'reason': request.reason})
    else:
        rows = labor_forecast(start.date(), end.date(), (defn.filters or {}).get('location_id'))

    rows = _apply_report_filters(rows, defn.filters)
    rows = _apply_report_sorting(rows, defn.sorting)
    columns = defn.columns or (list(rows[0]) if rows else [])
    return columns, [{column: row.get(column) for column in columns} for row in rows]


def rows_to_csv(columns, rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, delimiter=';')
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    return '\ufeff' + output.getvalue()


def emit_webhook(event_type, payload):
    ids = []
    for subscription in WebhookSubscription.objects.filter(active=True):
        events = subscription.events or []
        if '*' not in events and event_type not in events and not any(event.endswith('.*') and event_type.startswith(event[:-1]) for event in events):
            continue
        delivery = WebhookDelivery.objects.create(subscription=subscription, event_type=event_type, payload=payload)
        ids.append(str(delivery.id))
    if ids:
        from .premium_tasks import deliver_premium_webhook
        transaction.on_commit(lambda: [deliver_premium_webhook.delay(item_id) for item_id in ids])
    return ids


def deliver_webhook(delivery):
    raw = json.dumps({'event': delivery.event_type, 'created_at': delivery.created_at.isoformat(), 'data': delivery.payload}, separators=(',', ':'), ensure_ascii=False).encode()
    signature = hmac.new(delivery.subscription.signing_secret.encode(), raw, hashlib.sha256).hexdigest()
    delivery.attempts += 1
    try:
        response = requests.post(
            delivery.subscription.endpoint_url, data=raw,
            headers={'Content-Type': 'application/json', 'X-Aplus-Signature': f'sha256={signature}', 'X-Aplus-Event': delivery.event_type},
            timeout=15,
        )
        delivery.response_status = response.status_code
        delivery.response_body = response.text[:2000]
        if 200 <= response.status_code < 300:
            delivery.status = WebhookDelivery.Status.DELIVERED
            delivery.delivered_at = timezone.now()
            delivery.next_attempt_at = None
        else:
            delivery.status = WebhookDelivery.Status.FAILED
            delivery.next_attempt_at = timezone.now() + timedelta(minutes=min(120, 2 ** min(delivery.attempts, 7)))
    except requests.RequestException as exc:
        delivery.status = WebhookDelivery.Status.FAILED
        delivery.response_body = str(exc)[:2000]
        delivery.next_attempt_at = timezone.now() + timedelta(minutes=min(120, 2 ** min(delivery.attempts, 7)))
    delivery.save()
    return delivery.status


def integration_export(integration, start, end):
    records = [{
        'employee_number': entry.worker.employee_number,
        'email': entry.worker.user.email,
        'clock_in': entry.clock_in.isoformat(),
        'clock_out': entry.clock_out.isoformat() if entry.clock_out else None,
        'worked_minutes': entry.worked_minutes,
    } for entry in TimeEntry.objects.select_related('worker__user').filter(clock_in__gte=start, clock_in__lte=end, approved=True)]
    payload = {'provider': integration.provider, 'kind': integration.kind, 'from': start.isoformat(), 'to': end.isoformat(), 'records': records}
    if not integration.endpoint_url:
        return {'mode': 'export', 'payload': payload}
    headers = {'Content-Type': 'application/json'}
    for header, env_name in (integration.credential_env or {}).items():
        if os.getenv(str(env_name)):
            headers[str(header)] = os.getenv(str(env_name))
    response = requests.post(integration.endpoint_url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    integration.last_sync_at = timezone.now()
    integration.save(update_fields=['last_sync_at', 'updated_at'])
    return {'mode': 'push', 'status': response.status_code, 'count': len(records)}

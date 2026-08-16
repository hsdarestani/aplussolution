import csv, hashlib, hmac, io, json, os
from datetime import datetime, timedelta
from decimal import Decimal
import requests
from django.db import transaction
from django.utils import timezone
from .models import AuditLog, Availability, Shift, TimeEntry, TimeOffRequest, WorkerProfile
from .premium_models import DailyForecast, ReportDefinition, SchedulingPolicy, WebhookDelivery, WebhookSubscription
from .shift_slots import ShiftSlot


def get_policy():
    return SchedulingPolicy.objects.filter(active=True).first() or SchedulingPolicy.objects.create(name='Standard')


def hours(shift):
    return max(Decimal('0'), Decimal(str((shift.ends_at-shift.starts_at).total_seconds()/3600))-Decimal(str(shift.break_minutes or 0))/60)


def violations(worker, shift, policy=None):
    p=policy or get_policy(); out=[]
    required=set(shift.position.required_skills or [])
    if required and not required.issubset(set(worker.skills or [])): out.append('required_skills')
    if Availability.objects.filter(worker=worker,available=False,starts_at__lt=shift.ends_at,ends_at__gt=shift.starts_at).exists(): out.append('unavailable')
    if TimeOffRequest.objects.filter(worker=worker,status=TimeOffRequest.Status.APPROVED,starts_on__lte=shift.ends_at.date(),ends_on__gte=shift.starts_at.date()).exists(): out.append('approved_time_off')
    slots=list(ShiftSlot.objects.select_related('shift').filter(worker=worker,status=ShiftSlot.Status.CLAIMED).exclude(shift=shift))
    if any(s.shift.starts_at<shift.ends_at and s.shift.ends_at>shift.starts_at for s in slots): out.append('overlap')
    same=[s for s in slots if s.shift.starts_at.date()==shift.starts_at.date()]
    if same and not p.allow_multiple_shifts_per_day: out.append('multiple_shifts_per_day')
    for s in slots:
        other=s.shift
        if other.ends_at<=shift.starts_at:
            gap=Decimal(str((shift.starts_at-other.ends_at).total_seconds()/3600)); req=p.min_hours_same_day if other.ends_at.date()==shift.starts_at.date() else p.min_hours_between_days
            if gap<req: out.append('minimum_rest'); break
        if shift.ends_at<=other.starts_at:
            gap=Decimal(str((other.starts_at-shift.ends_at).total_seconds()/3600)); req=p.min_hours_same_day if shift.ends_at.date()==other.starts_at.date() else p.min_hours_between_days
            if gap<req: out.append('minimum_rest'); break
    if hours(shift)+sum((hours(s.shift) for s in same),Decimal('0'))>p.max_hours_per_day: out.append('max_hours_per_day')
    ws=(shift.starts_at-timedelta(days=shift.starts_at.weekday())).replace(hour=0,minute=0,second=0,microsecond=0); we=ws+timedelta(days=7)
    week=[s for s in slots if ws<=s.shift.starts_at<we]
    if hours(shift)+sum((hours(s.shift) for s in week),Decimal('0'))>p.max_hours_per_week: out.append('max_hours_per_week')
    if len({shift.starts_at.date(),*[s.shift.starts_at.date() for s in week]})>p.max_days_per_week: out.append('max_days_per_week')
    if p.respect_worker_monthly_hours and worker.monthly_hours:
        ms=shift.starts_at.replace(day=1,hour=0,minute=0,second=0,microsecond=0); me=(ms.replace(year=ms.year+1,month=1) if ms.month==12 else ms.replace(month=ms.month+1))
        month=[s for s in slots if ms<=s.shift.starts_at<me]
        if hours(shift)+sum((hours(s.shift) for s in month),Decimal('0'))>worker.monthly_hours: out.append('monthly_hours')
    return sorted(set(out))


def auto_schedule(start,end,apply=False,location_id=None,worker_ids=None):
    p=get_policy()
    if not p.auto_schedule_enabled: raise ValueError('Auto Scheduling ist deaktiviert.')
    qs=ShiftSlot.objects.select_related('shift__position','shift__location').filter(status=ShiftSlot.Status.OPEN,shift__starts_at__gte=start,shift__starts_at__lt=end,shift__status__in=[Shift.Status.DRAFT,Shift.Status.PUBLISHED])
    if location_id: qs=qs.filter(shift__location_id=location_id)
    slots=list(qs); slots.sort(key=lambda s:(0 if p.weekend_first and s.shift.starts_at.weekday()>=5 else 1,s.shift.starts_at))
    workers=WorkerProfile.objects.select_related('user').filter(active=True,user__is_active=True)
    if worker_ids: workers=workers.filter(id__in=worker_ids)
    workers=list(workers); rows=[]
    with transaction.atomic():
        for slot in slots:
            candidates=[]
            for w in workers:
                if violations(w,slot.shift,p): continue
                load=sum((hours(x.shift) for x in ShiftSlot.objects.select_related('shift').filter(worker=w,status=ShiftSlot.Status.CLAIMED,shift__starts_at__gte=start,shift__starts_at__lt=end)),Decimal('0'))
                preferred=Availability.objects.filter(worker=w,available=True,starts_at__lte=slot.shift.starts_at,ends_at__gte=slot.shift.ends_at).exists()
                candidates.append((load-(Decimal('2') if preferred else Decimal('0')),w.user.email,w))
            candidates.sort(key=lambda x:(x[0],x[1])); chosen=candidates[0][2] if candidates else None
            rows.append({'slot_id':str(slot.id),'shift_id':str(slot.shift_id),'worker_id':str(chosen.id) if chosen else None,'worker':(chosen.user.get_full_name() or chosen.user.email) if chosen else None,'candidate_count':len(candidates)})
            if apply and chosen:
                slot.worker=chosen; slot.status=ShiftSlot.Status.CLAIMED; slot.source='auto'; slot.claimed_at=timezone.now(); slot.save()
    return {'apply':apply,'assigned':sum(bool(r['worker_id']) for r in rows),'unfilled':sum(not r['worker_id'] for r in rows),'results':rows}


def labor_forecast(start,end,location_id=None):
    qs=DailyForecast.objects.select_related('location','metric').filter(date__gte=start,date__lte=end)
    if location_id: qs=qs.filter(location_id=location_id)
    rows=[]
    for f in qs:
        ds=timezone.make_aware(datetime.combine(f.date,datetime.min.time())); de=ds+timedelta(days=1); total_h=Decimal('0'); cost=Decimal('0')
        for slot in ShiftSlot.objects.select_related('shift','worker').filter(status=ShiftSlot.Status.CLAIMED,shift__location=f.location,shift__starts_at__lt=de,shift__ends_at__gt=ds):
            h=hours(slot.shift); rate=(slot.worker.tariff_hourly_rate or 0)+(slot.worker.extra_allowance or 0); total_h+=h; cost+=h*rate
        budget=f.labor_budget_amount or (f.projected_sales*f.labor_budget_percent/100 if f.projected_sales and f.labor_budget_percent else 0)
        rows.append({'id':str(f.id),'date':f.date.isoformat(),'location':f.location.name,'metric':f.metric.name if f.metric else None,'projected_units':str(f.projected_units),'projected_sales':str(f.projected_sales),'scheduled_hours':str(total_h),'scheduled_labor_cost':str(cost),'labor_budget':str(budget),'variance':str(Decimal(budget)-cost)})
    return rows


def run_report(defn,start,end):
    rows=[]
    if defn.kind=='shifts':
        for s in Shift.objects.select_related('location','position').filter(starts_at__gte=start,starts_at__lte=end):
            rows.append({'shift_id':str(s.id),'start':s.starts_at.isoformat(),'end':s.ends_at.isoformat(),'location':s.location.name,'position':s.position.name,'status':s.status,'required_count':s.required_count,'claimed_count':s.slots.filter(status=ShiftSlot.Status.CLAIMED).count()})
    elif defn.kind=='times':
        for t in TimeEntry.objects.select_related('worker__user','shift__location').filter(clock_in__gte=start,clock_in__lte=end):
            rows.append({'time_id':str(t.id),'worker':t.worker.user.get_full_name() or t.worker.user.email,'employee_number':t.worker.employee_number,'clock_in':t.clock_in.isoformat(),'clock_out':t.clock_out.isoformat() if t.clock_out else None,'worked_minutes':t.worked_minutes,'approved':t.approved,'location':t.shift.location.name if t.shift else None})
    elif defn.kind=='shift_history':
        for a in AuditLog.objects.select_related('actor').filter(created_at__gte=start,created_at__lte=end,object_type__icontains='shift'):
            rows.append({'timestamp':a.created_at.isoformat(),'actor':a.actor.email if a.actor else None,'action':a.action,'shift_id':a.object_id,'metadata':a.metadata})
    elif defn.kind=='users':
        for w in WorkerProfile.objects.select_related('user'):
            rows.append({'worker_id':str(w.id),'employee_number':w.employee_number,'name':w.user.get_full_name(),'email':w.user.email,'employment_type':w.employment_type,'monthly_hours':str(w.monthly_hours or ''),'skills':w.skills,'active':w.active})
    elif defn.kind=='time_off':
        for r in TimeOffRequest.objects.select_related('worker__user').filter(starts_on__lte=end.date(),ends_on__gte=start.date()):
            rows.append({'request_id':str(r.id),'worker':r.worker.user.get_full_name() or r.worker.user.email,'start':r.starts_on.isoformat(),'end':r.ends_on.isoformat(),'status':r.status,'reason':r.reason})
    else: rows=labor_forecast(start.date(),end.date(),(defn.filters or {}).get('location_id'))
    columns=defn.columns or (list(rows[0]) if rows else []); rows=[{c:r.get(c) for c in columns} for r in rows]
    return columns,rows


def rows_to_csv(columns,rows):
    out=io.StringIO(); w=csv.DictWriter(out,fieldnames=columns,delimiter=';'); w.writeheader()
    for row in rows: w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    return '\ufeff'+out.getvalue()


def emit_webhook(event_type,payload):
    ids=[]
    for sub in WebhookSubscription.objects.filter(active=True):
        events=sub.events or []
        if '*' not in events and event_type not in events and not any(e.endswith('.*') and event_type.startswith(e[:-1]) for e in events): continue
        d=WebhookDelivery.objects.create(subscription=sub,event_type=event_type,payload=payload); ids.append(str(d.id))
    if ids:
        from .premium_tasks import deliver_premium_webhook
        transaction.on_commit(lambda:[deliver_premium_webhook.delay(i) for i in ids])
    return ids


def deliver_webhook(d):
    raw=json.dumps({'event':d.event_type,'created_at':d.created_at.isoformat(),'data':d.payload},separators=(',',':'),ensure_ascii=False).encode(); sig=hmac.new(d.subscription.signing_secret.encode(),raw,hashlib.sha256).hexdigest(); d.attempts+=1
    try:
        r=requests.post(d.subscription.endpoint_url,data=raw,headers={'Content-Type':'application/json','X-Aplus-Signature':f'sha256={sig}','X-Aplus-Event':d.event_type},timeout=15); d.response_status=r.status_code; d.response_body=r.text[:2000]
        if 200<=r.status_code<300: d.status=WebhookDelivery.Status.DELIVERED; d.delivered_at=timezone.now(); d.next_attempt_at=None
        else: d.status=WebhookDelivery.Status.FAILED; d.next_attempt_at=timezone.now()+timedelta(minutes=min(120,2**min(d.attempts,7)))
    except requests.RequestException as e: d.status=WebhookDelivery.Status.FAILED; d.response_body=str(e)[:2000]; d.next_attempt_at=timezone.now()+timedelta(minutes=min(120,2**min(d.attempts,7)))
    d.save(); return d.status


def integration_export(integration,start,end):
    records=[{'employee_number':t.worker.employee_number,'email':t.worker.user.email,'clock_in':t.clock_in.isoformat(),'clock_out':t.clock_out.isoformat() if t.clock_out else None,'worked_minutes':t.worked_minutes} for t in TimeEntry.objects.select_related('worker__user').filter(clock_in__gte=start,clock_in__lte=end,approved=True)]
    payload={'provider':integration.provider,'kind':integration.kind,'from':start.isoformat(),'to':end.isoformat(),'records':records}
    if not integration.endpoint_url: return {'mode':'export','payload':payload}
    headers={'Content-Type':'application/json'}
    for header,env_name in (integration.credential_env or {}).items():
        if os.getenv(str(env_name)): headers[str(header)]=os.getenv(str(env_name))
    r=requests.post(integration.endpoint_url,json=payload,headers=headers,timeout=30); r.raise_for_status(); integration.last_sync_at=timezone.now(); integration.save(); return {'mode':'push','status':r.status_code,'count':len(records)}

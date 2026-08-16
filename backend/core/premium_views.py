import secrets
from datetime import timedelta
from dateutil.parser import isoparse
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Shift, TimeEntry, TimeOffRequest, User, WorkerProfile
from .permissions import IsAdmin, IsAdminOrManager
from .premium_auth import PublicApiKeyAuthentication, require_scope
from .premium_models import DailyForecast, ExternalIntegration, ForecastMetric, PublicApiKey, ReportDefinition, ScheduleTemplate, ScheduleTemplateShift, SchedulingPolicy, ShiftTag, ShiftTagLink, StaffCallout, TaskCompletion, TaskItem, TaskList, TaskRun, TimeOffCategory, TimeOffClassification, WebhookSubscription
from .premium_services import auto_schedule, emit_webhook, integration_export, labor_forecast, rows_to_csv, run_report
from .services import audit
from .shift_slots import ShiftSlot


def dt(value,fallback=None):
    if not value:return fallback
    value=isoparse(str(value)); return timezone.make_aware(value) if timezone.is_naive(value) else value

def date(value): return isoparse(str(value)).date() if value else None

def worker_for(request,explicit=None):
    if explicit and request.user.role in {User.Role.ADMIN,User.Role.MANAGER}: return get_object_or_404(WorkerProfile,pk=explicit)
    return get_object_or_404(WorkerProfile,user=request.user) if request.user.role==User.Role.WORKER else None


@api_view(['GET','PATCH'])
@permission_classes([IsAdminOrManager])
def scheduling_policy(request):
    p=SchedulingPolicy.objects.filter(active=True).first() or SchedulingPolicy.objects.create(name='Standard')
    fields=['name','min_hours_same_day','min_hours_between_days','max_days_in_row','max_days_per_week','max_hours_per_day','max_hours_per_week','respect_worker_monthly_hours','allow_multiple_shifts_per_day','allow_overlapping_open_shifts','labor_sharing_enabled','task_lists_enabled','auto_schedule_enabled','pickup_approval_required','weekend_first','timezone_toggle_enabled','default_timezone']
    if request.method=='PATCH':
        for f in fields:
            if f in request.data:setattr(p,f,request.data[f])
        p.save(); audit(request,'premium.scheduling_policy.updated',p)
    return Response({'id':str(p.id),**{f:getattr(p,f) for f in fields}})


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def auto_schedule_view(request):
    start=dt(request.data.get('start'),timezone.now()); end=dt(request.data.get('end'),start+timedelta(days=14))
    try: result=auto_schedule(start,end,bool(request.data.get('apply')),request.data.get('location_id'),request.data.get('worker_ids'))
    except ValueError as e:return Response({'detail':str(e)},status=409)
    audit(request,'premium.auto_schedule.applied' if result['apply'] else 'premium.auto_schedule.preview',request.user,{'assigned':result['assigned']}); return Response(result)


@api_view(['GET','POST'])
@permission_classes([IsAdminOrManager])
def tags(request):
    if request.method=='POST':
        row=ShiftTag.objects.create(name=request.data['name'],color=request.data.get('color') or '#2457E6'); return Response({'id':str(row.id)},status=201)
    return Response([{'id':str(x.id),'name':x.name,'color':x.color,'active':x.active} for x in ShiftTag.objects.all()])


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def set_shift_tags(request,shift_id):
    shift=get_object_or_404(Shift,pk=shift_id); ids=request.data.get('tag_ids') or []; ShiftTagLink.objects.filter(shift=shift).delete()
    for tag in ShiftTag.objects.filter(id__in=ids):ShiftTagLink.objects.create(shift=shift,tag=tag)
    return Response({'shift_id':str(shift.id),'tag_ids':[str(i) for i in ids]})


@api_view(['GET','POST'])
@permission_classes([IsAdminOrManager])
def schedule_templates(request):
    if request.method=='POST':
        row=ScheduleTemplate.objects.create(name=request.data.get('name') or 'Vorlage',location_id=request.data.get('location_id') or None,created_by=request.user)
        for item in request.data.get('items') or []:ScheduleTemplateShift.objects.create(template=row,weekday=item['weekday'],start_time=item['start_time'],end_time=item['end_time'],break_minutes=item.get('break_minutes') or 0,required_count=item.get('required_count') or 1,position_id=item['position_id'],notes=item.get('notes') or '')
        return Response({'id':str(row.id)},status=201)
    return Response([{'id':str(x.id),'name':x.name,'location_id':str(x.location_id) if x.location_id else None,'items':[{'id':str(i.id),'weekday':i.weekday,'start_time':i.start_time.isoformat(),'end_time':i.end_time.isoformat(),'position_id':str(i.position_id),'required_count':i.required_count} for i in x.items.all()]} for x in ScheduleTemplate.objects.prefetch_related('items').filter(active=True)])


@api_view(['GET','POST'])
@permission_classes([IsAuthenticated])
def task_lists(request):
    if request.method=='POST':
        if request.user.role not in {User.Role.ADMIN,User.Role.MANAGER}:return Response({'detail':'Keine Berechtigung.'},status=403)
        row=TaskList.objects.create(name=request.data.get('name') or 'Aufgabenliste',kind=request.data.get('kind') or TaskList.Kind.SHIFT,location_id=request.data.get('location_id') or None,created_by=request.user)
        for n,item in enumerate(request.data.get('items') or []):TaskItem.objects.create(task_list=row,title=item.get('title') or f'Aufgabe {n+1}',description=item.get('description') or '',required=item.get('required',True),sort_order=n)
        return Response({'id':str(row.id)},status=201)
    return Response([{'id':str(x.id),'name':x.name,'kind':x.kind,'items':[{'id':str(i.id),'title':i.title,'description':i.description,'required':i.required} for i in x.items.all()]} for x in TaskList.objects.prefetch_related('items').filter(active=True)])


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def task_assign(request,list_id):
    tl=get_object_or_404(TaskList,pk=list_id); shift=get_object_or_404(Shift,pk=request.data['shift_id']) if request.data.get('shift_id') else None; loc=request.data.get('location_id') or (shift.location_id if shift else tl.location_id)
    if not loc:return Response({'detail':'Einsatzort fehlt.'},status=400)
    run=TaskRun.objects.create(task_list=tl,shift=shift,location_id=loc,run_date=date(request.data.get('run_date')) or (shift.starts_at.date() if shift else timezone.localdate()),assigned_worker_id=request.data.get('worker_id') or None); return Response({'id':str(run.id)},status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def task_runs(request):
    qs=TaskRun.objects.select_related('task_list','location','shift').prefetch_related('task_list__items','completions')
    if request.user.role==User.Role.WORKER:
        w=get_object_or_404(WorkerProfile,user=request.user); qs=qs.filter(Q(assigned_worker=w)|Q(shift__slots__worker=w,shift__slots__status=ShiftSlot.Status.CLAIMED)).distinct()
    out=[]
    for r in qs[:200]:
        done={str(c.item_id):c for c in r.completions.all()}; out.append({'id':str(r.id),'name':r.task_list.name,'run_date':r.run_date.isoformat(),'shift_id':str(r.shift_id) if r.shift_id else None,'location':r.location.name,'closed_at':r.closed_at.isoformat() if r.closed_at else None,'items':[{'id':str(i.id),'title':i.title,'required':i.required,'completed':str(i.id) in done} for i in r.task_list.items.all()]})
    return Response(out)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def task_complete(request,run_id):
    run=get_object_or_404(TaskRun,pk=run_id); item=get_object_or_404(TaskItem,pk=request.data['item_id'],task_list=run.task_list)
    if request.user.role==User.Role.WORKER:
        w=get_object_or_404(WorkerProfile,user=request.user)
        if run.assigned_worker_id!=w.id and not (run.shift_id and run.shift.slots.filter(worker=w,status=ShiftSlot.Status.CLAIMED).exists()):return Response({'detail':'Keine Berechtigung.'},status=403)
    c,created=TaskCompletion.objects.get_or_create(run=run,item=item,defaults={'completed_by':request.user,'note':request.data.get('note') or ''}); required=set(run.task_list.items.filter(required=True).values_list('id',flat=True)); done=set(run.completions.values_list('item_id',flat=True))
    if required.issubset(done):run.closed_at=timezone.now();run.save()
    return Response({'created':created,'completed_at':c.completed_at.isoformat(),'run_closed':bool(run.closed_at)})


@api_view(['GET','POST'])
@permission_classes([IsAdminOrManager])
def forecasts(request):
    if request.method=='POST':
        metric=None
        if request.data.get('metric_name'):metric,_=ForecastMetric.objects.get_or_create(name=request.data['metric_name'],defaults={'unit':request.data.get('unit') or 'Einheit'})
        row,_=DailyForecast.objects.update_or_create(location_id=request.data['location_id'],date=date(request.data['date']),metric=metric,defaults={'projected_sales':request.data.get('projected_sales') or 0,'projected_units':request.data.get('projected_units') or 0,'labor_budget_percent':request.data.get('labor_budget_percent') or 0,'labor_budget_amount':request.data.get('labor_budget_amount') or 0,'notes':request.data.get('notes') or ''});return Response({'id':str(row.id)},status=201)
    start=date(request.query_params.get('start')) or timezone.localdate();end=date(request.query_params.get('end')) or start+timedelta(days=30);return Response(labor_forecast(start,end,request.query_params.get('location_id')))


@api_view(['GET','POST'])
@permission_classes([IsAuthenticated])
def callouts(request):
    if request.method=='POST':
        w=worker_for(request,request.data.get('worker_id'));shift=get_object_or_404(Shift,pk=request.data['shift_id']);now=timezone.now()
        if not w:return Response({'detail':'Mitarbeiter fehlt.'},status=400)
        if shift.starts_at<now or shift.starts_at>now+timedelta(hours=24):return Response({'detail':'Callouts sind nur innerhalb von 24 Stunden vor Schichtbeginn möglich.'},status=400)
        slot=shift.slots.filter(worker=w,status=ShiftSlot.Status.CLAIMED).first()
        if not slot:return Response({'detail':'Keine übernommene Schicht.'},status=400)
        with transaction.atomic():
            row=StaffCallout.objects.create(shift=shift,worker=w,slot=slot,reason=request.data.get('reason') or '');slot.worker=None;slot.status=ShiftSlot.Status.OPEN;slot.source='callout';slot.released_at=timezone.now();slot.save()
        return Response({'id':str(row.id),'status':row.status},status=201)
    qs=StaffCallout.objects.select_related('shift__location','worker__user','covered_by__user')
    if request.user.role==User.Role.WORKER:qs=qs.filter(worker__user=request.user)
    return Response([{'id':str(x.id),'shift_id':str(x.shift_id),'worker':x.worker.user.get_full_name() or x.worker.user.email,'starts_at':x.shift.starts_at.isoformat(),'location':x.shift.location.name,'reason':x.reason,'status':x.status,'covered_by':x.covered_by.user.email if x.covered_by else None} for x in qs[:200]])


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def callout_cover(request,pk):
    row=get_object_or_404(StaffCallout,pk=pk);w=get_object_or_404(WorkerProfile,pk=request.data['worker_id']);slot=row.shift.slots.filter(status=ShiftSlot.Status.OPEN).first()
    if not slot:return Response({'detail':'Keine offene Kapazität.'},status=409)
    slot.worker=w;slot.status=ShiftSlot.Status.CLAIMED;slot.source='callout_cover';slot.claimed_at=timezone.now();slot.save();row.covered_by=w;row.decided_by=request.user;row.status=StaffCallout.Status.COVERED;row.resolved_at=timezone.now();row.save();return Response({'status':row.status})


@api_view(['GET','POST'])
@permission_classes([IsAdminOrManager])
def time_off_categories(request):
    if request.method=='POST':
        x=TimeOffCategory.objects.create(name=request.data['name'],code=request.data['code'],paid=bool(request.data.get('paid')),requires_approval=request.data.get('requires_approval',True));return Response({'id':str(x.id)},status=201)
    return Response([{'id':str(x.id),'name':x.name,'code':x.code,'paid':x.paid,'requires_approval':x.requires_approval,'active':x.active} for x in TimeOffCategory.objects.all()])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def classify_time_off(request,pk):
    item=get_object_or_404(TimeOffRequest,pk=pk)
    if request.user.role==User.Role.WORKER and item.worker.user_id!=request.user.id:return Response({'detail':'Keine Berechtigung.'},status=403)
    cat=get_object_or_404(TimeOffCategory,pk=request.data['category_id'],active=True);row,_=TimeOffClassification.objects.update_or_create(request=item,defaults={'category':cat});return Response({'category_id':str(row.category_id)})


@api_view(['GET','POST'])
@permission_classes([IsAdminOrManager])
def report_definitions(request):
    if request.method=='POST':
        x=ReportDefinition.objects.create(name=request.data.get('name') or 'Bericht',kind=request.data['kind'],columns=request.data.get('columns') or [],filters=request.data.get('filters') or {},sorting=request.data.get('sorting') or [],owner=request.user,shared=bool(request.data.get('shared')));return Response({'id':str(x.id)},status=201)
    qs=ReportDefinition.objects.filter(Q(owner=request.user)|Q(shared=True));return Response([{'id':str(x.id),'name':x.name,'kind':x.kind,'columns':x.columns,'filters':x.filters,'sorting':x.sorting,'shared':x.shared} for x in qs])


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def report_run(request,pk):
    x=get_object_or_404(ReportDefinition,pk=pk);start=dt(request.data.get('start'),timezone.now()-timedelta(days=90));end=dt(request.data.get('end'),timezone.now()+timedelta(days=90));cols,rows=run_report(x,start,end)
    if request.data.get('format')=='csv':
        r=HttpResponse(rows_to_csv(cols,rows),content_type='text/csv; charset=utf-8');r['Content-Disposition']=f'attachment; filename="{x.kind}.csv"';return r
    return Response({'columns':cols,'rows':rows,'count':len(rows)})


@api_view(['GET','POST'])
@permission_classes([IsAdmin])
def api_keys(request):
    if request.method=='POST':
        x,raw=PublicApiKey.issue(name=request.data.get('name') or 'API Key',scopes=request.data.get('scopes') or ['*'],created_by=request.user,expires_at=dt(request.data.get('expires_at')) if request.data.get('expires_at') else None);return Response({'id':str(x.id),'prefix':x.prefix,'scopes':x.scopes,'key':raw,'warning':'Dieser Key wird nur einmal angezeigt.'},status=201)
    return Response([{'id':str(x.id),'name':x.name,'prefix':x.prefix,'scopes':x.scopes,'active':x.active,'last_used_at':x.last_used_at.isoformat() if x.last_used_at else None} for x in PublicApiKey.objects.all()])


@api_view(['DELETE'])
@permission_classes([IsAdmin])
def api_key_revoke(request,pk):
    x=get_object_or_404(PublicApiKey,pk=pk);x.active=False;x.save();return Response(status=204)


@api_view(['GET','POST'])
@permission_classes([IsAdmin])
def webhooks(request):
    if request.method=='POST':
        secret=request.data.get('signing_secret') or secrets.token_urlsafe(32);x=WebhookSubscription.objects.create(name=request.data.get('name') or 'Webhook',endpoint_url=request.data['endpoint_url'],signing_secret=secret,events=request.data.get('events') or ['*'],created_by=request.user);return Response({'id':str(x.id),'signing_secret':secret,'events':x.events},status=201)
    return Response([{'id':str(x.id),'name':x.name,'endpoint_url':x.endpoint_url,'events':x.events,'active':x.active,'deliveries':x.deliveries.count()} for x in WebhookSubscription.objects.all()])


@api_view(['POST'])
@permission_classes([IsAdmin])
def webhook_test(request,pk):
    get_object_or_404(WebhookSubscription,pk=pk);ids=emit_webhook('system.test',{'subscription_id':str(pk),'message':'A+ Solution webhook test'});return Response({'queued':bool(ids),'deliveries':ids})


@api_view(['GET','POST'])
@permission_classes([IsAdmin])
def integrations(request):
    if request.method=='POST':
        x=ExternalIntegration.objects.create(name=request.data.get('name') or request.data.get('provider') or 'Integration',kind=request.data.get('kind') or ExternalIntegration.Kind.GENERIC,provider=request.data.get('provider') or 'generic',endpoint_url=request.data.get('endpoint_url') or '',credential_env=request.data.get('credential_env') or {},config=request.data.get('config') or {},created_by=request.user);return Response({'id':str(x.id)},status=201)
    return Response([{'id':str(x.id),'name':x.name,'kind':x.kind,'provider':x.provider,'endpoint_url':x.endpoint_url,'credential_env':x.credential_env,'config':x.config,'active':x.active,'last_sync_at':x.last_sync_at.isoformat() if x.last_sync_at else None} for x in ExternalIntegration.objects.all()])


@api_view(['POST'])
@permission_classes([IsAdmin])
def integration_sync(request,pk):
    x=get_object_or_404(ExternalIntegration,pk=pk,active=True)
    try:return Response(integration_export(x,dt(request.data.get('start'),timezone.now()-timedelta(days=31)),dt(request.data.get('end'),timezone.now())))
    except Exception as e:return Response({'detail':str(e)},status=502)


@api_view(['GET','POST'])
@authentication_classes([PublicApiKeyAuthentication])
@permission_classes([IsAuthenticated])
def public_api_resource(request,resource):
    if request.method=='GET':
        require_scope(request,f'{resource}:read')
        if resource=='users':rows=[{'id':str(w.id),'employee_number':w.employee_number,'email':w.user.email,'name':w.user.get_full_name(),'skills':w.skills,'active':w.active} for w in WorkerProfile.objects.select_related('user')[:1000]]
        elif resource=='shifts':rows=[{'id':str(s.id),'client_id':str(s.client_id),'location_id':str(s.location_id),'position_id':str(s.position_id),'starts_at':s.starts_at.isoformat(),'ends_at':s.ends_at.isoformat(),'status':s.status,'is_open':s.is_open,'required_count':s.required_count,'assignments':[{'slot_id':str(z.id),'worker_id':str(z.worker_id) if z.worker_id else None,'status':z.status} for z in s.slots.all()]} for s in Shift.objects.prefetch_related('slots')[:1000]]
        elif resource=='times':rows=[{'id':str(t.id),'worker_id':str(t.worker_id),'shift_id':str(t.shift_id) if t.shift_id else None,'clock_in':t.clock_in.isoformat(),'clock_out':t.clock_out.isoformat() if t.clock_out else None,'approved':t.approved} for t in TimeEntry.objects.all()[:1000]]
        elif resource=='time_off':rows=[{'id':str(t.id),'worker_id':str(t.worker_id),'starts_on':t.starts_on.isoformat(),'ends_on':t.ends_on.isoformat(),'status':t.status,'reason':t.reason} for t in TimeOffRequest.objects.all()[:1000]]
        elif resource=='tasks':rows=[{'id':str(r.id),'name':r.task_list.name,'run_date':r.run_date.isoformat(),'shift_id':str(r.shift_id) if r.shift_id else None,'closed_at':r.closed_at.isoformat() if r.closed_at else None} for r in TaskRun.objects.select_related('task_list')[:1000]]
        else:return Response({'detail':'Unbekannte Ressource.'},status=404)
        return Response({'count':len(rows),'results':rows})
    require_scope(request,f'{resource}:write')
    if resource=='shifts':
        s=Shift.objects.create(client_id=request.data['client_id'],location_id=request.data['location_id'],position_id=request.data['position_id'],starts_at=dt(request.data['starts_at']),ends_at=dt(request.data['ends_at']),break_minutes=request.data.get('break_minutes') or 0,status=request.data.get('status') or Shift.Status.DRAFT,is_open=request.data.get('is_open',True),notes=request.data.get('notes') or '',required_count=request.data.get('required_count') or 1);return Response({'id':str(s.id)},status=201)
    if resource=='time_off':
        x=TimeOffRequest.objects.create(worker_id=request.data['worker_id'],starts_on=date(request.data['starts_on']),ends_on=date(request.data['ends_on']),reason=request.data.get('reason') or '');return Response({'id':str(x.id)},status=201)
    return Response({'detail':'Schreibzugriff wird für diese Ressource nicht unterstützt.'},status=405)

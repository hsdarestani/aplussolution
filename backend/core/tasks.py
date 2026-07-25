from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from .models import Contract,Notification,Shift,User
@shared_task
def send_contract_reminders():
    today=timezone.localdate(); sent=0
    for days in (30,7):
        for contract in Contract.objects.filter(ends_on=today+timedelta(days=days),status__in=['ready','sent','signed']):
            for user in User.objects.filter(role__in=['admin','manager'],is_active=True): Notification.objects.get_or_create(user=user,kind=f'contract-{days}',action_url=f'/contracts/{contract.id}',title=f'Vertrag endet in {days} Tagen',body=contract.title)
            sent+=1
    for contract in Contract.objects.filter(reminder_date=today,status__in=['draft','ready','sent','signed']):
        for user in User.objects.filter(role__in=['admin','manager'],is_active=True): Notification.objects.get_or_create(user=user,kind='contract-reminder',action_url=f'/contracts/{contract.id}',title='Vertragserinnerung',body=contract.title)
        sent+=1
    if sent: send_mail(f'A+ Solution: {sent} Vertragserinnerungen',f'Im Portal sind {sent} Vertragserinnerungen fällig.',settings.DEFAULT_FROM_EMAIL,[settings.ADMIN_NOTIFICATION_EMAIL],fail_silently=True)
    return sent
@shared_task
def send_shift_reminders():
    now=timezone.now(); shifts=Shift.objects.filter(starts_at__range=(now+timedelta(hours=23,minutes=30),now+timedelta(hours=24,minutes=30)),worker__isnull=False,status__in=['published','confirmed']).select_related('worker__user','location')
    for shift in shifts: Notification.objects.get_or_create(user=shift.worker.user,kind='shift-24h',action_url='/schedule',title='Dein Einsatz beginnt morgen',body=f'{shift.starts_at:%d.%m.%Y %H:%M} – {shift.location.name}')
    return shifts.count()

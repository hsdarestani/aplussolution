from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Contract, Notification, Shift, User


def contract_recipients(contract):
    recipients = list(User.objects.filter(role__in=['admin', 'manager'], is_active=True))
    if contract.worker_id and contract.worker.user.is_active:
        recipients.append(contract.worker.user)
    if contract.client_id:
        recipients.extend(contract.client.contacts.filter(is_active=True))
    unique = {}
    for user in recipients:
        unique[user.pk] = user
    return list(unique.values())


def create_contract_notice(contract, kind, title):
    count = 0
    email_recipients = []
    for user in contract_recipients(contract):
        _, created = Notification.objects.get_or_create(
            user=user,
            kind=f'{kind}-{contract.id}',
            defaults={
                'action_url': '/contracts',
                'title': title,
                'body': contract.title,
            },
        )
        count += int(created)
        if user.email:
            email_recipients.append(user.email)
    if email_recipients:
        send_mail(
            f'A+ Solution: {title}',
            f'{contract.title}\n\nBitte im A+ Solution Portal prüfen.',
            settings.DEFAULT_FROM_EMAIL,
            sorted(set(email_recipients)),
            fail_silently=True,
        )
    return count


@shared_task
def send_contract_reminders():
    today = timezone.localdate()
    sent = 0
    for days in (30, 7):
        contracts = Contract.objects.filter(
            ends_on=today + timedelta(days=days),
            status__in=['ready', 'sent', 'signed'],
        ).select_related('worker__user', 'client').prefetch_related('client__contacts')
        for contract in contracts:
            sent += create_contract_notice(
                contract,
                f'contract-{days}',
                f'Vertrag endet in {days} Tagen',
            )
    contracts = Contract.objects.filter(
        reminder_date=today,
        status__in=['draft', 'ready', 'sent', 'signed'],
    ).select_related('worker__user', 'client').prefetch_related('client__contacts')
    for contract in contracts:
        sent += create_contract_notice(contract, 'contract-reminder', 'Vertragserinnerung')
    if sent:
        send_mail(
            f'A+ Solution: {sent} Portal-Benachrichtigungen',
            f'Im Portal wurden {sent} Vertragserinnerungen an die zuständigen Personen verteilt.',
            settings.DEFAULT_FROM_EMAIL,
            [settings.ADMIN_NOTIFICATION_EMAIL],
            fail_silently=True,
        )
    return sent


@shared_task
def send_shift_reminders():
    now = timezone.now()
    shifts = Shift.objects.filter(
        starts_at__range=(
            now + timedelta(hours=23, minutes=30),
            now + timedelta(hours=24, minutes=30),
        ),
        worker__isnull=False,
        status__in=['published', 'confirmed'],
    ).select_related('worker__user', 'location', 'position')
    count = 0
    for shift in shifts:
        _, created = Notification.objects.get_or_create(
            user=shift.worker.user,
            kind=f'shift-24h-{shift.id}',
            defaults={
                'action_url': '/schedule',
                'title': 'Dein Einsatz beginnt morgen',
                'body': f'{shift.starts_at:%d.%m.%Y %H:%M} – {shift.location.name} – {shift.position.name}',
            },
        )
        count += int(created)
        if created and shift.worker.user.email:
            send_mail(
                'A+ Solution: Dein Einsatz beginnt morgen',
                f'{shift.starts_at:%d.%m.%Y %H:%M}\n{shift.location.name}\n{shift.position.name}',
                settings.DEFAULT_FROM_EMAIL,
                [shift.worker.user.email],
                fail_silently=True,
            )
    return count

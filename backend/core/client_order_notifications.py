from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import ClientOrder, Notification, User


@receiver(post_save, sender=ClientOrder, dispatch_uid='aplus_client_order_admin_notification')
def notify_admins_about_client_order(sender, instance: ClientOrder, created: bool, **kwargs):
    if not created or not instance.created_by_id:
        return
    creator = instance.created_by
    if not creator or creator.role != User.Role.CLIENT:
        return

    account_name = creator.get_full_name() or creator.username or creator.email
    when = timezone.localtime(instance.starts_at).strftime('%d.%m.%y %H:%M') if instance.starts_at else 'Termin offen'
    location = instance.location.name if instance.location_id and instance.location else 'Einsatzort offen'
    for recipient in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
        Notification.objects.get_or_create(
            user=recipient,
            kind=f'client-order-request-{instance.id}',
            defaults={
                'title': 'Neue Kundenanfrage',
                'body': f'{instance.client.name} · {account_name} · {when} · {location}',
                'action_url': '/operations',
            },
        )

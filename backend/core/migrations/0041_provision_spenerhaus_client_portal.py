from django.db import migrations


EMAIL = 'marcingorgon@aol.com'
HOTEL_NAME = 'Hotel Spenerhaus'


def provision_spenerhaus_client_portal(apps, schema_editor):
    User = apps.get_model('core', 'User')
    ClientCompany = apps.get_model('core', 'ClientCompany')
    Location = apps.get_model('core', 'Location')
    ClientPortalAccess = apps.get_model('core', 'ClientPortalAccess')

    hotels = list(
        ClientCompany.objects.filter(name__iexact=HOTEL_NAME, active=True).order_by('created_at')[:2]
    )
    if len(hotels) != 1:
        raise RuntimeError('Expected exactly one active Hotel Spenerhaus customer.')
    hotel = hotels[0]

    locations = list(
        Location.objects.filter(client=hotel, name__iexact=HOTEL_NAME, active=True).order_by('created_at')[:2]
    )
    if len(locations) != 1:
        raise RuntimeError('Expected exactly one active Hotel Spenerhaus location.')
    location = locations[0]

    user = User.objects.filter(email__iexact=EMAIL).first()
    if user and user.role != 'client':
        raise RuntimeError('Requested email already belongs to a non client user.')
    if user and user.client_companies.exclude(pk=hotel.pk).exists():
        raise RuntimeError('Requested email is already linked to another customer.')

    if not user:
        user = User.objects.create(
            email=EMAIL,
            username=EMAIL,
            role='client',
            is_active=True,
            is_onboarded=False,
            locale='de',
            password='!',
        )
    else:
        user.email = EMAIL
        user.username = EMAIL
        user.role = 'client'
        user.is_active = True
        user.locale = 'de'
        user.save(update_fields=['email', 'username', 'role', 'is_active', 'locale'])

    hotel.contacts.add(user)

    ClientPortalAccess.objects.update_or_create(
        user=user,
        defaults={
            'client': hotel,
            'label': HOTEL_NAME,
            'read_only': True,
            'location_scope': location,
            'capabilities': {'schedule': True},
        },
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0040_timeentry_break_minutes'),
    ]

    operations = [
        migrations.RunPython(provision_spenerhaus_client_portal, noop_reverse),
    ]

import unicodedata
import uuid

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations, models
import django.db.models.deletion


def _key(value):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode('ascii').lower()
    return ''.join(ch for ch in text if ch.isalnum())


def _find_client(ClientCompany, needle):
    target = _key(needle)
    for client in ClientCompany.objects.filter(active=True).order_by('created_at'):
        current = _key(client.name)
        if target == current or target in current or current in target:
            return client
    return None


def _find_user(User, first_name, last_name, username):
    username_key = _key(username)
    first_key = _key(first_name)
    last_key = _key(last_name)
    for user in User.objects.filter(role='client').order_by('date_joined', 'id'):
        identity = _key(f'{user.username} {str(user.email).split("@")[0]} {user.first_name} {user.last_name}')
        if username_key and username_key in identity:
            return user
        if first_key and last_key and first_key in identity and last_key in identity:
            return user
    return None


def _ensure_user(User, *, first_name, last_name, username, email):
    user = _find_user(User, first_name, last_name, username)
    if not user:
        user = User.objects.filter(email__iexact=email).first()
    created = False
    if not user:
        user = User.objects.create(
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
            role='client',
            is_active=True,
            is_onboarded=False,
            password=make_password(None),
        )
        created = True
    else:
        updates = {
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'role': 'client',
            'is_active': True,
        }
        for field, value in updates.items():
            setattr(user, field, value)
        user.save(update_fields=list(updates))
    return user, created


def _attach(ClientCompany, ClientPortalAccess, client, user, *, label, read_only=False, location_scope=None):
    if not client or not user:
        return
    for other in ClientCompany.objects.filter(contacts=user).exclude(pk=client.pk):
        other.contacts.remove(user)
    client.contacts.add(user)
    ClientPortalAccess.objects.update_or_create(
        user=user,
        defaults={
            'client': client,
            'label': label,
            'read_only': read_only,
            'location_scope': location_scope,
            'capabilities': {'schedule': True} if read_only else {},
        },
    )


def seed_client_portal_accounts(apps, schema_editor):
    User = apps.get_model('core', 'User')
    ClientCompany = apps.get_model('core', 'ClientCompany')
    Location = apps.get_model('core', 'Location')
    ClientPortalAccess = apps.get_model('core', 'ClientPortalAccess')

    marthas = _find_client(ClientCompany, 'Marthas') or _find_client(ClientCompany, "Martha's Finest")
    stadthaus = _find_client(ClientCompany, 'Stadthaus am Markt')

    if marthas:
        julia, _ = _ensure_user(
            User,
            first_name='Julia',
            last_name='Stahl',
            username='Julia.stahl',
            email='julia.stahl@marthas.portal.invalid',
        )
        _attach(ClientCompany, ClientPortalAccess, marthas, julia, label='Julia', read_only=False)

        claudia, _ = _ensure_user(
            User,
            first_name='Claudia',
            last_name='Fröhling',
            username='Claudia.fröhling',
            email='claudia.froehling@marthas.portal.invalid',
        )
        _attach(ClientCompany, ClientPortalAccess, marthas, claudia, label='Claudia', read_only=False)

        academy_location = None
        for location in Location.objects.filter(client=marthas, active=True).order_by('created_at'):
            if _key(location.name) == _key('Evangelische Akademie'):
                academy_location = location
                break
        academy, _ = _ensure_user(
            User,
            first_name='Evangelische',
            last_name='Akademie',
            username='Evangelische Akademie',
            email='evangelische.akademie@marthas.portal.invalid',
        )
        _attach(
            ClientCompany,
            ClientPortalAccess,
            marthas,
            academy,
            label='Evangelische Akademie',
            read_only=True,
            location_scope=academy_location,
        )

    if stadthaus:
        kerstin, _ = _ensure_user(
            User,
            first_name='Kerstin',
            last_name='Albrecht',
            username='Kerstin Albrecht',
            email='kerstin.albrecht@stadthaus.portal.invalid',
        )
        _attach(ClientCompany, ClientPortalAccess, stadthaus, kerstin, label='Kerstin', read_only=False)


def noop_reverse(apps, schema_editor):
    # Portal identities can receive customer activity after deployment. Do not
    # remove or detach them automatically on rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0037_recover_musa_time_entries_by_wiw_identity'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientPortalAccess',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('label', models.CharField(blank=True, max_length=200)),
                ('read_only', models.BooleanField(default=False)),
                ('capabilities', models.JSONField(blank=True, default=dict)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='portal_accesses', to='core.clientcompany')),
                ('location_scope', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='portal_accesses', to='core.location')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='client_portal_access', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['client__name', 'user__first_name', 'user__last_name'],
                'indexes': [models.Index(fields=['client', 'read_only'], name='client_access_scope_idx')],
            },
        ),
        migrations.CreateModel(
            name='ClientShiftChangeRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('request_type', models.CharField(choices=[('change', 'Zeit / Datum ändern'), ('cancel', 'Schicht stornieren')], max_length=20)),
                ('requested_starts_at', models.DateTimeField(blank=True, null=True)),
                ('requested_ends_at', models.DateTimeField(blank=True, null=True)),
                ('note', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('pending', 'Offen'), ('approved', 'Genehmigt'), ('rejected', 'Abgelehnt')], default='pending', max_length=20)),
                ('original_snapshot', models.JSONField(blank=True, default=dict)),
                ('decision_snapshot', models.JSONField(blank=True, default=dict)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('admin_note', models.TextField(blank=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shift_change_requests', to='core.clientcompany')),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='decided_client_shift_change_requests', to=settings.AUTH_USER_MODEL)),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='client_shift_change_requests', to=settings.AUTH_USER_MODEL)),
                ('shift', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='client_change_requests', to='core.shift')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['status', 'created_at'], name='client_req_status_idx'),
                    models.Index(fields=['shift', 'status'], name='client_req_shift_idx'),
                ],
            },
        ),
        migrations.RunPython(seed_client_portal_accounts, noop_reverse),
    ]

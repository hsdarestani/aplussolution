from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def path(rel):
    return ROOT / rel


def replace_once(rel, old, new):
    p = path(rel)
    text = p.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{rel}: expected one match, found {count}: {old[:80]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


def regex_once(rel, pattern, replacement):
    p = path(rel)
    text = p.read_text(encoding='utf-8')
    new, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'{rel}: regex match count {count}: {pattern[:80]!r}')
    p.write_text(new, encoding='utf-8')


# ---------------------------------------------------------------------------
# Backend: per-assignee confirmation state
# ---------------------------------------------------------------------------
replace_once(
    'backend/core/models.py',
    "    required_count = models.PositiveIntegerField(default=1)\n    published_at = models.DateTimeField(blank=True, null=True)",
    "    required_count = models.PositiveIntegerField(default=1)\n    confirmation_required = models.BooleanField(default=False)\n    published_at = models.DateTimeField(blank=True, null=True)",
)

announcement_models = '''    read_at = models.DateTimeField(blank=True, null=True)\n\n\nclass Announcement(TimestampedModel):\n    title = models.CharField(max_length=200, default='Mitteilung')\n    body = models.TextField(blank=True)\n    attachment = models.FileField(upload_to='announcements/%Y/%m/', blank=True, null=True)\n    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_announcements')\n    recipients = models.ManyToManyField(User, through='AnnouncementRecipient', related_name='received_announcements')\n    sent_at = models.DateTimeField(default=timezone.now)\n\n    class Meta:\n        ordering = ['-sent_at', '-created_at']\n\n\nclass AnnouncementRecipient(TimestampedModel):\n    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name='recipient_links')\n    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='announcement_links')\n    notification = models.ForeignKey(Notification, on_delete=models.SET_NULL, null=True, blank=True, related_name='announcement_links')\n    read_at = models.DateTimeField(blank=True, null=True)\n\n    class Meta:\n        unique_together = ('announcement', 'user')\n        ordering = ['created_at']\n\n\nclass AuditLog'''
replace_once(
    'backend/core/models.py',
    "    read_at = models.DateTimeField(blank=True, null=True)\n\n\nclass AuditLog",
    announcement_models,
)

replace_once(
    'backend/core/shift_slots.py',
    "    class Status(models.TextChoices):\n        OPEN = 'open', 'Offen'\n        CLAIMED = 'claimed', 'Übernommen'\n        CANCELLED = 'cancelled', 'Storniert'\n\n    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='slots')",
    "    class Status(models.TextChoices):\n        OPEN = 'open', 'Offen'\n        CLAIMED = 'claimed', 'Übernommen'\n        CANCELLED = 'cancelled', 'Storniert'\n\n    class ConfirmationStatus(models.TextChoices):\n        PENDING = 'pending', 'Ausstehend'\n        CONFIRMED = 'confirmed', 'Bestätigt'\n        REJECTED = 'rejected', 'Abgelehnt'\n\n    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='slots')",
)
replace_once(
    'backend/core/shift_slots.py',
    "    claimed_at = models.DateTimeField(blank=True, null=True)\n    released_at = models.DateTimeField(blank=True, null=True)\n\n    class Meta:",
    "    claimed_at = models.DateTimeField(blank=True, null=True)\n    released_at = models.DateTimeField(blank=True, null=True)\n    confirmation_status = models.CharField(max_length=20, choices=ConfirmationStatus.choices, default=ConfirmationStatus.CONFIRMED)\n    confirmation_requested_at = models.DateTimeField(blank=True, null=True)\n    confirmation_decided_at = models.DateTimeField(blank=True, null=True)\n\n    class Meta:",
)

replace_once(
    'backend/core/shift_api.py',
    "                    'id': str(slot.worker_id),\n                    'name': slot.worker.user.get_full_name() or slot.worker.user.email,\n                    'employee_number': slot.worker.employee_number,\n                    'avatar': avatar,",
    "                    'id': str(slot.worker_id),\n                    'slot_id': str(slot.id),\n                    'name': slot.worker.user.get_full_name() or slot.worker.user.email,\n                    'employee_number': slot.worker.employee_number,\n                    'avatar': avatar,\n                    'confirmation_status': slot.confirmation_status,\n                    'confirmation_label': slot.get_confirmation_status_display(),\n                    'confirmation_requested_at': slot.confirmation_requested_at,\n                    'confirmation_decided_at': slot.confirmation_decided_at,\n                    'is_me': bool(request and request.user.is_authenticated and slot.worker.user_id == request.user.id),",
)
replace_once(
    'backend/core/shift_api.py',
    "            'required_count', 'open_count', 'filled_count', 'assigned_workers',",
    "            'required_count', 'confirmation_required', 'open_count', 'filled_count', 'assigned_workers',",
)

replace_once(
    'backend/core/shift_service.py',
    "    slot.claimed_at = timezone.now()\n    slot.released_at = None\n    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'updated_at'])",
    "    now = timezone.now()\n    slot.claimed_at = now\n    slot.released_at = None\n    # Claiming an OpenShift is itself an explicit acceptance.\n    slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED\n    slot.confirmation_requested_at = now if shift.confirmation_required else None\n    slot.confirmation_decided_at = now\n    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'confirmation_status', 'confirmation_requested_at', 'confirmation_decided_at', 'updated_at'])",
)
replace_once(
    'backend/core/shift_service.py',
    "    slot.source = 'worker_release'\n    slot.released_at = timezone.now()\n    slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'updated_at'])",
    "    slot.source = 'worker_release'\n    slot.released_at = timezone.now()\n    slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED\n    slot.confirmation_requested_at = None\n    slot.confirmation_decided_at = None\n    slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'confirmation_status', 'confirmation_requested_at', 'confirmation_decided_at', 'updated_at'])",
)

old_update = '''    def perform_update(self, serializer):\n        with transaction.atomic():\n            obj = serializer.save(worker=None)\n            ensure_slots(obj)\n            if obj.status == Shift.Status.PUBLISHED:\n                ensure_shift_publish_allowed(obj)\n                if not obj.published_at:\n                    obj.published_at = timezone.now()\n                    obj.save(update_fields=['published_at', 'updated_at'])\n            refresh_shift_state(obj)\n            audit(self.request, 'staffing_demand.updated', obj, {'required_count': obj.required_count})\n'''
new_update = '''    def perform_update(self, serializer):\n        previous_confirmation_required = bool(serializer.instance.confirmation_required)\n        with transaction.atomic():\n            obj = serializer.save(worker=None)\n            ensure_slots(obj)\n            if obj.status == Shift.Status.PUBLISHED:\n                ensure_shift_publish_allowed(obj)\n                if not obj.published_at:\n                    obj.published_at = timezone.now()\n                    obj.save(update_fields=['published_at', 'updated_at'])\n            if previous_confirmation_required != bool(obj.confirmation_required):\n                now = timezone.now()\n                for slot in claimed_slots(obj).select_related('worker__user'):\n                    if obj.confirmation_required:\n                        slot.confirmation_status = ShiftSlot.ConfirmationStatus.PENDING\n                        slot.confirmation_requested_at = now\n                        slot.confirmation_decided_at = None\n                        Notification.objects.create(\n                            user=slot.worker.user,\n                            kind=f'shift-confirmation-required-{slot.id}-{int(now.timestamp())}',\n                            title='Schicht bestätigen',\n                            body=f'{timezone.localtime(obj.starts_at):%d.%m.%Y %H:%M} – {obj.location.name}',\n                            action_url='/schedule',\n                        )\n                    else:\n                        slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED\n                        slot.confirmation_requested_at = None\n                        slot.confirmation_decided_at = now\n                    slot.save(update_fields=['confirmation_status', 'confirmation_requested_at', 'confirmation_decided_at', 'updated_at'])\n            refresh_shift_state(obj)\n            audit(self.request, 'staffing_demand.updated', obj, {\n                'required_count': obj.required_count,\n                'confirmation_required': obj.confirmation_required,\n            })\n'''
replace_once('backend/core/shift_views.py', old_update, new_update)

replace_once(
    'backend/core/shift_views.py',
    "                    slot.source = 'admin_release'\n                    slot.released_at = timezone.now()\n                    slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'updated_at'])",
    "                    slot.source = 'admin_release'\n                    slot.released_at = timezone.now()\n                    slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED\n                    slot.confirmation_requested_at = None\n                    slot.confirmation_decided_at = None\n                    slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'confirmation_status', 'confirmation_requested_at', 'confirmation_decided_at', 'updated_at'])",
)
replace_once(
    'backend/core/shift_views.py',
    "                slot.claimed_at = timezone.now()\n                slot.released_at = None\n                slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'updated_at'])",
    "                now = timezone.now()\n                slot.claimed_at = now\n                slot.released_at = None\n                slot.confirmation_status = (\n                    ShiftSlot.ConfirmationStatus.PENDING if shift.confirmation_required\n                    else ShiftSlot.ConfirmationStatus.CONFIRMED\n                )\n                slot.confirmation_requested_at = now if shift.confirmation_required else None\n                slot.confirmation_decided_at = None if shift.confirmation_required else now\n                slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'confirmation_status', 'confirmation_requested_at', 'confirmation_decided_at', 'updated_at'])",
)
replace_once(
    'backend/core/shift_views.py',
    "                        'title': 'Neue Schicht zugeteilt',\n                        'body': f'{timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M} – {shift.location.name}',",
    "                        'title': 'Schicht bestätigen' if shift.confirmation_required else 'Neue Schicht zugeteilt',\n                        'body': f'{timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M} – {shift.location.name}',",
)

confirmation_action = '''    @action(detail=True, methods=['post'])\n    def confirmation(self, request, pk=None):\n        next_status = str(request.data.get('status', '')).strip().lower()\n        allowed = {\n            ShiftSlot.ConfirmationStatus.PENDING,\n            ShiftSlot.ConfirmationStatus.CONFIRMED,\n            ShiftSlot.ConfirmationStatus.REJECTED,\n        }\n        if next_status not in allowed:\n            return Response({'detail': 'status muss pending, confirmed oder rejected sein.'}, status=400)\n\n        with transaction.atomic():\n            shift = Shift.objects.select_for_update().select_related('location', 'position').get(pk=pk)\n            if not shift.confirmation_required:\n                return Response({'detail': 'Für diese Schicht ist keine Bestätigung erforderlich.'}, status=400)\n\n            if request.user.role == User.Role.WORKER:\n                if next_status == ShiftSlot.ConfirmationStatus.PENDING:\n                    return Response({'detail': 'Mitarbeiter können nur bestätigen oder ablehnen.'}, status=400)\n                slot = ShiftSlot.objects.select_for_update().select_related('worker__user').filter(\n                    shift=shift, worker=request.user.worker_profile, status=ShiftSlot.Status.CLAIMED\n                ).first()\n                if not slot:\n                    return Response({'detail': 'Keine zugewiesene Schicht gefunden.'}, status=404)\n                actor_is_worker = True\n            elif request.user.role in {User.Role.ADMIN, User.Role.MANAGER}:\n                slot_id = str(request.data.get('slot_id', '')).strip()\n                slot = ShiftSlot.objects.select_for_update().select_related('worker__user').filter(\n                    pk=slot_id, shift=shift, status=ShiftSlot.Status.CLAIMED, worker__isnull=False\n                ).first()\n                if not slot:\n                    return Response({'detail': 'Zuweisung wurde nicht gefunden.'}, status=404)\n                actor_is_worker = False\n            else:\n                return Response({'detail': 'Keine Berechtigung für Schichtbestätigungen.'}, status=403)\n\n            now = timezone.now()\n            slot.confirmation_status = next_status\n            if next_status == ShiftSlot.ConfirmationStatus.PENDING:\n                slot.confirmation_requested_at = now\n                slot.confirmation_decided_at = None\n            else:\n                slot.confirmation_requested_at = slot.confirmation_requested_at or now\n                slot.confirmation_decided_at = now\n            slot.save(update_fields=['confirmation_status', 'confirmation_requested_at', 'confirmation_decided_at', 'updated_at'])\n\n            label = slot.get_confirmation_status_display()\n            if actor_is_worker:\n                for admin in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):\n                    Notification.objects.create(\n                        user=admin,\n                        kind=f'shift-confirmation-response-{slot.id}-{next_status}-{int(now.timestamp())}',\n                        title=f'Schicht {label.lower()}',\n                        body=f'{slot.worker.user.get_full_name() or slot.worker.user.email} · {timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M} · {shift.location.name}',\n                        action_url='/schedule',\n                    )\n            else:\n                Notification.objects.create(\n                    user=slot.worker.user,\n                    kind=f'shift-confirmation-admin-{slot.id}-{next_status}-{int(now.timestamp())}',\n                    title='Schichtbestätigung aktualisiert',\n                    body=f'{label} · {timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M} · {shift.location.name}',\n                    action_url='/schedule',\n                )\n            audit(request, 'shift.confirmation_changed', shift, {\n                'slot': str(slot.id),\n                'worker': str(slot.worker_id),\n                'status': next_status,\n            })\n\n        return Response(self.get_serializer(self.base_queryset().get(pk=pk)).data)\n\n'''
replace_once(
    'backend/core/shift_views.py',
    "    @action(detail=True, methods=['post'])\n    def claim(self, request, pk=None):",
    confirmation_action + "    @action(detail=True, methods=['post'])\n    def claim(self, request, pk=None):",
)

# ---------------------------------------------------------------------------
# Backend: one-way Mitteilungen with existing Notification -> native Push path
# ---------------------------------------------------------------------------
announcement_api = '''import json\n\nfrom django.db import transaction\nfrom django.utils import timezone\nfrom rest_framework import serializers, status, viewsets\nfrom rest_framework.decorators import action\nfrom rest_framework.parsers import FormParser, JSONParser, MultiPartParser\nfrom rest_framework.permissions import IsAuthenticated\nfrom rest_framework.response import Response\n\nfrom .models import Announcement, AnnouncementRecipient, Notification, User\nfrom .permissions import IsAdminOrManager\nfrom .services import audit\n\n\nclass AnnouncementSerializer(serializers.ModelSerializer):\n    created_by_name = serializers.SerializerMethodField()\n    recipient_count = serializers.SerializerMethodField()\n    read_count = serializers.SerializerMethodField()\n    recipients_detail = serializers.SerializerMethodField()\n    is_read = serializers.SerializerMethodField()\n\n    class Meta:\n        model = Announcement\n        fields = [\n            'id', 'title', 'body', 'attachment', 'created_by', 'created_by_name',\n            'sent_at', 'created_at', 'updated_at', 'recipient_count', 'read_count',\n            'recipients_detail', 'is_read',\n        ]\n        read_only_fields = ['created_by', 'sent_at']\n\n    def get_created_by_name(self, obj):\n        if not obj.created_by:\n            return 'Administration'\n        return obj.created_by.get_full_name() or obj.created_by.email\n\n    def get_recipient_count(self, obj):\n        return obj.recipient_links.count()\n\n    def get_read_count(self, obj):\n        return obj.recipient_links.filter(read_at__isnull=False).count()\n\n    def get_recipients_detail(self, obj):\n        request = self.context.get('request')\n        if not request or request.user.role not in {User.Role.ADMIN, User.Role.MANAGER}:\n            return []\n        return [\n            {\n                'id': str(link.user_id),\n                'name': link.user.get_full_name() or link.user.email,\n                'role': link.user.role,\n                'read_at': link.read_at,\n            }\n            for link in obj.recipient_links.select_related('user').all()\n        ]\n\n    def get_is_read(self, obj):\n        request = self.context.get('request')\n        if not request or request.user.role in {User.Role.ADMIN, User.Role.MANAGER}:\n            return False\n        return obj.recipient_links.filter(user=request.user, read_at__isnull=False).exists()\n\n    def validate_attachment(self, uploaded):\n        if not uploaded:\n            return uploaded\n        if getattr(uploaded, 'size', 0) > 20 * 1024 * 1024:\n            raise serializers.ValidationError('Der Anhang darf maximal 20 MB groß sein.')\n        name = str(getattr(uploaded, 'name', '') or '').lower()\n        allowed = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt', '.png', '.jpg', '.jpeg', '.webp')\n        if not name.endswith(allowed):\n            raise serializers.ValidationError('Erlaubt sind Bilder, PDF, Word, Excel/CSV und Textdateien.')\n        return uploaded\n\n\nclass AnnouncementViewSet(viewsets.ModelViewSet):\n    queryset = Announcement.objects.none()\n    serializer_class = AnnouncementSerializer\n    permission_classes = [IsAuthenticated]\n    parser_classes = [MultiPartParser, FormParser, JSONParser]\n    http_method_names = ['get', 'post', 'head', 'options']\n\n    def get_queryset(self):\n        qs = Announcement.objects.select_related('created_by').prefetch_related('recipient_links__user').all()\n        if self.request.user.role in {User.Role.ADMIN, User.Role.MANAGER}:\n            return qs\n        return qs.filter(recipient_links__user=self.request.user).distinct()\n\n    def get_permissions(self):\n        if self.action == 'create':\n            return [IsAdminOrManager()]\n        return [IsAuthenticated()]\n\n    @staticmethod\n    def _truthy(value):\n        return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}\n\n    def _recipient_ids(self, request):\n        if hasattr(request.data, 'getlist'):\n            values = request.data.getlist('recipient_ids')\n        else:\n            values = request.data.get('recipient_ids', [])\n            if not isinstance(values, list):\n                values = [values] if values else []\n        if len(values) == 1 and isinstance(values[0], str) and values[0].strip().startswith('['):\n            try:\n                values = json.loads(values[0])\n            except json.JSONDecodeError:\n                pass\n        return [str(value).strip() for value in values if str(value).strip()]\n\n    def create(self, request, *args, **kwargs):\n        serializer = self.get_serializer(data=request.data)\n        serializer.is_valid(raise_exception=True)\n        if not str(serializer.validated_data.get('body', '') or '').strip() and not serializer.validated_data.get('attachment'):\n            return Response({'detail': 'Bitte Text oder einen Anhang hinzufügen.'}, status=400)\n\n        all_recipients = self._truthy(request.data.get('all_recipients'))\n        if all_recipients:\n            targets = User.objects.filter(\n                is_active=True, role__in=[User.Role.WORKER, User.Role.CLIENT]\n            ).exclude(email__iendswith='@sync.invalid').order_by('last_name', 'first_name', 'email')\n        else:\n            ids = self._recipient_ids(request)\n            targets = User.objects.filter(\n                id__in=ids, is_active=True, role__in=[User.Role.WORKER, User.Role.CLIENT]\n            ).exclude(email__iendswith='@sync.invalid').order_by('last_name', 'first_name', 'email')\n\n        targets = list(targets)\n        if not targets:\n            return Response({'detail': 'Bitte mindestens einen aktiven Empfänger auswählen.'}, status=400)\n\n        with transaction.atomic():\n            announcement = serializer.save(\n                created_by=request.user,\n                sent_at=timezone.now(),\n                title=str(serializer.validated_data.get('title') or '').strip() or 'Mitteilung',\n            )\n            for recipient in targets:\n                notification = Notification.objects.create(\n                    user=recipient,\n                    kind=f'announcement-{announcement.id}',\n                    title=announcement.title,\n                    body=(announcement.body or 'Neue Mitteilung mit Anhang')[:180],\n                    action_url=f'/?view=messages&announcement={announcement.id}',\n                )\n                AnnouncementRecipient.objects.create(\n                    announcement=announcement, user=recipient, notification=notification\n                )\n            audit(request, 'announcement.sent', announcement, {\n                'recipient_count': len(targets),\n                'all_recipients': all_recipients,\n            })\n\n        output = self.get_serializer(announcement)\n        return Response(output.data, status=status.HTTP_201_CREATED)\n\n    @action(detail=True, methods=['post'])\n    def read(self, request, pk=None):\n        announcement = self.get_object()\n        if request.user.role in {User.Role.ADMIN, User.Role.MANAGER}:\n            return Response(self.get_serializer(announcement).data)\n        link = announcement.recipient_links.filter(user=request.user).select_related('notification').first()\n        if not link:\n            return Response({'detail': 'Mitteilung wurde nicht gefunden.'}, status=404)\n        now = timezone.now()\n        if not link.read_at:\n            link.read_at = now\n            link.save(update_fields=['read_at', 'updated_at'])\n        if link.notification and not link.notification.read_at:\n            link.notification.read_at = now\n            link.notification.save(update_fields=['read_at', 'updated_at'])\n        return Response(self.get_serializer(announcement).data)\n'''
path('backend/core/announcement_api.py').write_text(announcement_api, encoding='utf-8')

replace_once(
    'backend/core/urls.py',
    'from . import admin_center_views, advanced_views, akten_views,',
    'from . import admin_center_views, advanced_views, akten_views, announcement_api,',
)
replace_once(
    'backend/core/urls.py',
    "    ('ratings', client_portal_views.ClientSafeRatingViewSet),\n    ('conversations', views.ConversationViewSet),",
    "    ('ratings', client_portal_views.ClientSafeRatingViewSet),\n    ('announcements', announcement_api.AnnouncementViewSet),\n    ('conversations', views.ConversationViewSet),",
)

migration = '''import django.db.models.deletion\nimport django.utils.timezone\nfrom django.db import migrations, models\n\n\nclass Migration(migrations.Migration):\n    dependencies = [('core', '0013_scope_workforce_master_data')]\n\n    operations = [\n        migrations.AddField(\n            model_name='shift',\n            name='confirmation_required',\n            field=models.BooleanField(default=False),\n        ),\n        migrations.AddField(\n            model_name='shiftslot',\n            name='confirmation_status',\n            field=models.CharField(\n                choices=[('pending', 'Ausstehend'), ('confirmed', 'Bestätigt'), ('rejected', 'Abgelehnt')],\n                default='confirmed', max_length=20,\n            ),\n        ),\n        migrations.AddField(\n            model_name='shiftslot',\n            name='confirmation_requested_at',\n            field=models.DateTimeField(blank=True, null=True),\n        ),\n        migrations.AddField(\n            model_name='shiftslot',\n            name='confirmation_decided_at',\n            field=models.DateTimeField(blank=True, null=True),\n        ),\n        migrations.CreateModel(\n            name='Announcement',\n            fields=[\n                ('id', models.UUIDField(primary_key=True, serialize=False, editable=False)),\n                ('created_at', models.DateTimeField(auto_now_add=True)),\n                ('updated_at', models.DateTimeField(auto_now=True)),\n                ('title', models.CharField(default='Mitteilung', max_length=200)),\n                ('body', models.TextField(blank=True)),\n                ('attachment', models.FileField(blank=True, null=True, upload_to='announcements/%Y/%m/')),\n                ('sent_at', models.DateTimeField(default=django.utils.timezone.now)),\n                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sent_announcements', to='core.user')),\n            ],\n            options={'ordering': ['-sent_at', '-created_at']},\n        ),\n        migrations.CreateModel(\n            name='AnnouncementRecipient',\n            fields=[\n                ('id', models.UUIDField(primary_key=True, serialize=False, editable=False)),\n                ('created_at', models.DateTimeField(auto_now_add=True)),\n                ('updated_at', models.DateTimeField(auto_now=True)),\n                ('read_at', models.DateTimeField(blank=True, null=True)),\n                ('announcement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recipient_links', to='core.announcement')),\n                ('notification', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='announcement_links', to='core.notification')),\n                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='announcement_links', to='core.user')),\n            ],\n            options={'ordering': ['created_at'], 'unique_together': {('announcement', 'user')}},\n        ),\n        migrations.AddField(\n            model_name='announcement',\n            name='recipients',\n            field=models.ManyToManyField(related_name='received_announcements', through='core.AnnouncementRecipient', to='core.user'),\n        ),\n    ]\n'''
# UUID defaults must match the TimestampedModel schema used by the project.
migration = migration.replace("import django.db.models.deletion\n", "import uuid\n\nimport django.db.models.deletion\n")
migration = migration.replace("models.UUIDField(primary_key=True, serialize=False, editable=False)", "models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)")
path('backend/core/migrations/0014_phase6_confirmations_announcements.py').write_text(migration, encoding='utf-8')

backend_tests = '''from datetime import timedelta\n\nimport pytest\nfrom django.core.files.uploadedfile import SimpleUploadedFile\nfrom django.utils import timezone\n\nfrom core.models import Announcement, AnnouncementRecipient, Notification\n\n\n@pytest.mark.django_db\ndef test_confirmation_required_assignment_is_pending_and_worker_can_confirm(\n    auth_admin, auth_worker, admin_user, worker_user, company, location, position\n):\n    starts_at = timezone.now() + timedelta(days=2)\n    created = auth_admin.post('/api/shifts/', {\n        'client': str(company.id), 'location': str(location.id), 'position': str(position.id),\n        'starts_at': starts_at.isoformat(), 'ends_at': (starts_at + timedelta(hours=4)).isoformat(),\n        'required_count': 1, 'break_minutes': 0, 'status': 'draft', 'confirmation_required': True,\n    }, format='json')\n    assert created.status_code == 201, created.data\n\n    assigned = auth_admin.post(f"/api/shifts/{created.data['id']}/assign/", {\n        'workers': [str(worker_user.worker_profile.id)], 'publish_remaining': True,\n    }, format='json')\n    assert assigned.status_code == 200, assigned.data\n    worker = assigned.data['assigned_workers'][0]\n    assert worker['confirmation_status'] == 'pending'\n    assert worker['confirmation_label'] == 'Ausstehend'\n    assert worker['slot_id']\n    assert Notification.objects.filter(user=worker_user, title='Schicht bestätigen').exists()\n\n    confirmed = auth_worker.post(f"/api/shifts/{created.data['id']}/confirmation/", {'status': 'confirmed'}, format='json')\n    assert confirmed.status_code == 200, confirmed.data\n    mine = next(item for item in confirmed.data['assigned_workers'] if item['is_me'])\n    assert mine['confirmation_status'] == 'confirmed'\n    assert Notification.objects.filter(user=admin_user, kind__startswith='shift-confirmation-response-').exists()\n\n    reset = auth_admin.post(f"/api/shifts/{created.data['id']}/confirmation/", {\n        'slot_id': worker['slot_id'], 'status': 'pending',\n    }, format='json')\n    assert reset.status_code == 200, reset.data\n    assert reset.data['assigned_workers'][0]['confirmation_status'] == 'pending'\n\n\n@pytest.mark.django_db\ndef test_admin_sends_one_way_announcement_with_attachment_and_push_notification(\n    auth_admin, auth_worker, worker_user\n):\n    attachment = SimpleUploadedFile('einsatz.pdf', b'%PDF-1.4 phase6', content_type='application/pdf')\n    sent = auth_admin.post('/api/announcements/', {\n        'title': 'Wichtige Mitteilung',\n        'body': 'Bitte vor dem Einsatz lesen.',\n        'all_recipients': 'false',\n        'recipient_ids': [str(worker_user.id)],\n        'attachment': attachment,\n    }, format='multipart')\n    assert sent.status_code == 201, sent.data\n    assert sent.data['recipient_count'] == 1\n    assert sent.data['read_count'] == 0\n    announcement = Announcement.objects.get(pk=sent.data['id'])\n    link = AnnouncementRecipient.objects.get(announcement=announcement, user=worker_user)\n    assert link.notification_id\n    assert Notification.objects.filter(pk=link.notification_id, kind=f'announcement-{announcement.id}').exists()\n\n    inbox = auth_worker.get('/api/announcements/')\n    assert inbox.status_code == 200\n    rows = inbox.data.get('results', inbox.data)\n    assert len(rows) == 1\n    assert rows[0]['title'] == 'Wichtige Mitteilung'\n    assert rows[0]['is_read'] is False\n\n    read = auth_worker.post(f'/api/announcements/{announcement.id}/read/', {}, format='json')\n    assert read.status_code == 200\n    assert read.data['is_read'] is True\n    link.refresh_from_db()\n    assert link.read_at is not None\n\n    forbidden = auth_worker.post('/api/announcements/', {\n        'title': 'Nicht erlaubt', 'body': 'Antwort', 'recipient_ids': [str(worker_user.id)]\n    }, format='json')\n    assert forbidden.status_code == 403\n'''
path('backend/tests/test_phase6_confirmations_announcements.py').write_text(backend_tests, encoding='utf-8')

# ---------------------------------------------------------------------------
# Frontend: confirmation controls in every calendar view
# ---------------------------------------------------------------------------
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "const [form,setForm]=useState<any>({required_count:1,break_minutes:0,publish_now:true,workers:[]});",
    "const [form,setForm]=useState<any>({required_count:1,break_minutes:0,publish_now:true,confirmation_required:false,workers:[]});",
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "function create(){setEditing(undefined);setForm({required_count:1,break_minutes:0,publish_now:true,workers:[]});setModal(true);}",
    "function create(){setEditing(undefined);setForm({required_count:1,break_minutes:0,publish_now:true,confirmation_required:false,workers:[]});setModal(true);}",
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "const p:any={client:form.client,location:form.location,position:form.position,starts_at:form.starts_at,ends_at:form.ends_at,break_minutes:Number(form.break_minutes||0),required_count:requiredCount,notes:form.notes||'',status:baseStatus};",
    "const p:any={client:form.client,location:form.location,position:form.position,starts_at:form.starts_at,ends_at:form.ends_at,break_minutes:Number(form.break_minutes||0),required_count:requiredCount,confirmation_required:!!form.confirmation_required,notes:form.notes||'',status:baseStatus};",
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "  function confirmRelease(){const id=releaseTarget?.id;setReleaseTarget(undefined);if(id) void act(`shifts/${id}/release/`,'Schicht freigegeben.');}",
    "  async function setConfirmation(item:any,status:'pending'|'confirmed'|'rejected',slotId?:string){setBusy(true);try{await api(`shifts/${item.id}/confirmation/`,{method:'POST',body:JSON.stringify({status,...(slotId?{slot_id:slotId}:{})})});setToast(status==='confirmed'?'Schicht bestätigt.':status==='rejected'?'Schicht abgelehnt.':'Bestätigung erneut angefordert.');await load();}catch(e:any){setToast(e.message);}finally{setBusy(false);}}\n  function confirmRelease(){const id=releaseTarget?.id;setReleaseTarget(undefined);if(id) void act(`shifts/${id}/release/`,'Schicht freigegeben.');}",
)

confirmation_renderer = '''  const confirmationLabel=(status:string)=>status==='pending'?'Ausstehend':status==='rejected'?'Abgelehnt':'Bestätigt';\n  const confirmationColor=(status:string)=>status==='pending'?'warning':status==='rejected'?'danger':'success';\n  const renderConfirmationPanel=(item:any,compact=false)=>{\n    if(!item.confirmation_required) return null;\n    const assigned=item.assigned_workers||[];\n    const targets=isManager(user)?assigned:assigned.filter((worker:any)=>worker.is_me);\n    if(!targets.length) return <div className="sv2-confirmation-panel"><small>Bestätigung erforderlich · noch keine Zuweisung</small></div>;\n    return <div className={`sv2-confirmation-panel ${compact?'compact':''}`} data-testid="shift-confirmations">{targets.map((worker:any)=><div className="sv2-confirmation-row" key={worker.slot_id||worker.id}>\n      <span className="sv2-confirmation-person">{isManager(user)?worker.name:'Meine Bestätigung'}</span>\n      <IonBadge color={confirmationColor(worker.confirmation_status)}>{confirmationLabel(worker.confirmation_status)}</IonBadge>\n      {workerView&&worker.is_me&&worker.confirmation_status==='pending'&&<span className="sv2-confirmation-actions"><IonButton size="small" disabled={busy} onClick={event=>{event.stopPropagation();void setConfirmation(item,'confirmed');}}>Bestätigen</IonButton><IonButton size="small" fill="outline" color="danger" disabled={busy} onClick={event=>{event.stopPropagation();void setConfirmation(item,'rejected');}}>Ablehnen</IonButton></span>}\n      {isManager(user)&&!compact&&<span className="sv2-confirmation-actions admin"><IonButton size="small" fill="clear" disabled={busy||worker.confirmation_status==='pending'} onClick={event=>{event.stopPropagation();void setConfirmation(item,'pending',worker.slot_id);}}>Ausstehend</IonButton><IonButton size="small" fill="clear" color="success" disabled={busy||worker.confirmation_status==='confirmed'} onClick={event=>{event.stopPropagation();void setConfirmation(item,'confirmed',worker.slot_id);}}>Bestätigt</IonButton><IonButton size="small" fill="clear" color="danger" disabled={busy||worker.confirmation_status==='rejected'} onClick={event=>{event.stopPropagation();void setConfirmation(item,'rejected',worker.slot_id);}}>Abgelehnt</IonButton></span>}\n    </div>)}</div>;\n  };\n'''
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "  const renderShiftDetails=(item:any,compact=false)=><div className={`sv2-event-details ${compact?'compact':''}`} data-testid=\"shift-card-details\">",
    confirmation_renderer + "  const renderShiftDetails=(item:any,compact=false)=><div className={`sv2-event-details ${compact?'compact':''}`} data-testid=\"shift-card-details\">",
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "    <div className=\"sv2-event-line sv2-profile-line\" data-field=\"profile\"><IonIcon icon={personCircleOutline}/><span className=\"sv2-field-copy\"><small>Profilbild</small>{renderWorkerAvatars(item,compact)}</span></div>\n  </div>;",
    "    <div className=\"sv2-event-line sv2-profile-line\" data-field=\"profile\"><IonIcon icon={personCircleOutline}/><span className=\"sv2-field-copy\"><small>Profilbild</small>{renderWorkerAvatars(item,compact)}</span></div>\n    {renderConfirmationPanel(item,compact)}\n  </div>;",
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "      <IonTextarea className=\"full\" fill=\"outline\" label=\"Hinweise für Mitarbeiter\" labelPlacement=\"floating\" value={form.notes} onIonInput={e=>setForm({...form,notes:val(e)})}/><label className=\"sv2-toggle full\">",
    "      <IonTextarea className=\"full\" fill=\"outline\" label=\"Hinweise für Mitarbeiter\" labelPlacement=\"floating\" value={form.notes} onIonInput={e=>setForm({...form,notes:val(e)})}/><label className=\"sv2-toggle full\">Bestätigung durch zugewiesene Mitarbeiter erforderlich <IonToggle checked={!!form.confirmation_required} onIonChange={e=>setForm({...form,confirmation_required:e.detail.checked})}/></label><label className=\"sv2-toggle full\">",
)

schedule_css = path('frontend/src/schedule-v2.css').read_text(encoding='utf-8')
schedule_css += '''\n\n/* Phase 6: per-assignee confirmation state */\n.sv2-confirmation-panel{grid-column:1/-1;display:flex;flex-direction:column;gap:6px;margin-top:4px;padding-top:8px;border-top:1px solid rgba(120,130,150,.18)}\n.sv2-confirmation-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}\n.sv2-confirmation-person{font-size:12px;font-weight:700;min-width:110px}\n.sv2-confirmation-actions{display:inline-flex;gap:4px;flex-wrap:wrap}\n.sv2-confirmation-actions ion-button{min-height:28px;margin:0}\n.sv2-confirmation-panel.compact .sv2-confirmation-person{display:none}\n.sv2-confirmation-panel.compact{padding-top:4px;gap:3px}\n@media(max-width:700px){.sv2-confirmation-actions.admin{width:100%}.sv2-confirmation-row{align-items:flex-start}}\n'''
path('frontend/src/schedule-v2.css').write_text(schedule_css, encoding='utf-8')

# ---------------------------------------------------------------------------
# Frontend: replace two-way Chat UI with one-way Mitteilungen
# ---------------------------------------------------------------------------
replace_once('frontend/src/App.tsx', '  chatbubblesOutline,', '  megaphoneOutline,')
replace_once('frontend/src/App.tsx', '  sendOutline,\n', '')
replace_once('frontend/src/App.tsx', '  messages: chatbubblesOutline,', '  messages: megaphoneOutline,')
replace_once(
    'frontend/src/App.tsx',
    '// Übersicht -> Dienstplan -> Zeiterfassung -> Lohn/Dokumente -> Chat -> Anfragen -> Stammdaten.',
    '// Übersicht -> Dienstplan -> Zeiterfassung -> Lohn/Dokumente -> Mitteilungen -> Anfragen -> Stammdaten.',
)
# All role navigation labels should use the product term Mitteilungen.
app_path = path('frontend/src/App.tsx')
app_text = app_path.read_text(encoding='utf-8').replace("['messages', 'Nachrichten']", "['messages', 'Mitteilungen']")
app_text = app_text.replace("messages: 'Chat',", "messages: 'Mitteilungen',")
app_path.write_text(app_text, encoding='utf-8')

announcements_component = r'''function Announcements({ user }: { user: User }) {
  const [rows, setRows] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [selected, setSelected] = useState<string>();
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<any>({ title: '', body: '', recipients: [], all_recipients: true, attachment: null });
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');

  const manager = isManager(user);
  const recipientCandidates = useMemo(
    () => users.filter((person: any) => person.is_active !== false && ['worker', 'client'].includes(person.role) && !String(person.email || '').endsWith('@sync.invalid')),
    [users],
  );

  const load = async () => {
    try {
      if (manager) {
        const [announcementData, userData] = await Promise.all([api('announcements/'), api('users/')]);
        const list = unpack(announcementData);
        setRows(list);
        setUsers(unpack(userData));
        setSelected((current) => current && list.some((item: any) => item.id === current) ? current : list[0]?.id);
      } else {
        const announcementData = await api('announcements/');
        const list = unpack(announcementData);
        setRows(list);
        setSelected((current) => current && list.some((item: any) => item.id === current) ? current : list[0]?.id);
      }
    } catch (reason: any) {
      setToast(reason.message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  async function sendAnnouncement() {
    if (!form.body?.trim() && !form.attachment) {
      setToast('Bitte Text oder einen Anhang hinzufügen.');
      return;
    }
    if (!form.all_recipients && !(form.recipients || []).length) {
      setToast('Bitte mindestens einen Empfänger auswählen.');
      return;
    }
    setBusy(true);
    try {
      const payload = new FormData();
      payload.append('title', form.title?.trim() || 'Mitteilung');
      payload.append('body', form.body || '');
      payload.append('all_recipients', form.all_recipients ? 'true' : 'false');
      (form.recipients || []).forEach((id: string) => payload.append('recipient_ids', id));
      if (form.attachment) payload.append('attachment', form.attachment);
      const result: any = await api('announcements/', { method: 'POST', body: payload });
      setModal(false);
      setForm({ title: '', body: '', recipients: [], all_recipients: true, attachment: null });
      await load();
      setSelected(result.id);
      setToast(`Mitteilung an ${result.recipient_count || 0} Empfänger versendet. Push wurde ausgelöst.`);
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy(false);
    }
  }

  async function choose(item: any) {
    setSelected(item.id);
    if (!manager && !item.is_read) {
      try {
        await api(`announcements/${item.id}/read/`, { method: 'POST', body: '{}' });
        setRows((current) => current.map((row) => row.id === item.id ? { ...row, is_read: true } : row));
      } catch {
        // Reading the Mitteilung is still possible if the acknowledgement request is temporarily offline.
      }
    }
  }

  const active = rows.find((row) => row.id === selected);

  return (
    <>
      <Title
        title="Mitteilungen"
        text={manager ? 'Einweg-Mitteilungen an Mitarbeiter und Kunden – inklusive Datei, Push und Versandhistorie.' : 'Mitteilungen der A+ Solution Administration. Antworten sind nicht erforderlich.'}
        action={manager ? (
          <IonButton data-testid="announcement-create" onClick={() => setModal(true)}>
            <IonIcon slot="start" icon={addOutline} />
            Neue Mitteilung
          </IonButton>
        ) : undefined}
      />

      <div className="columns" data-testid="announcements-view">
        <div className="panel">
          <div className="section-head"><div><h3>{manager ? 'Versandhistorie' : 'Posteingang'}</h3><p>{rows.length} Mitteilungen</p></div></div>
          {rows.map((item) => (
            <button type="button" className={`row announcement-row ${item.id === selected ? 'active' : ''}`} key={item.id} onClick={() => void choose(item)}>
              <IonIcon icon={megaphoneOutline} />
              <div className="grow">
                <b>{item.title || 'Mitteilung'}</b>
                <p>{String(item.body || 'Mit Anhang').slice(0, 100)}</p>
                <small>{dateTime(item.sent_at)} · {item.created_by_name}</small>
              </div>
              {manager ? <IonBadge>{item.recipient_count} Empfänger</IonBadge> : !item.is_read ? <IonBadge color="primary">Neu</IonBadge> : <IonBadge color="medium">Gelesen</IonBadge>}
            </button>
          ))}
          {!rows.length && <Empty>Noch keine Mitteilungen.</Empty>}
        </div>

        <div className="panel">
          {active ? (
            <div data-testid="announcement-detail">
              <div className="section-head">
                <div><small>MITTEILUNG</small><h3>{active.title || 'Mitteilung'}</h3><p>{dateTime(active.sent_at)} · {active.created_by_name}</p></div>
                {manager && <IonBadge color="success">{active.read_count}/{active.recipient_count} gelesen</IonBadge>}
              </div>
              <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.65 }}>{active.body || 'Diese Mitteilung enthält einen Anhang.'}</p>
              {active.attachment && <p><a href={active.attachment} target="_blank" rel="noreferrer">Anhang öffnen / herunterladen</a></p>}
              {manager && active.recipients_detail?.length > 0 && (
                <div className="panel subtle-panel">
                  <b>Empfänger</b>
                  <p>{active.recipients_detail.map((person: any) => `${person.name}${person.read_at ? ' ✓' : ''}`).join(' · ')}</p>
                </div>
              )}
              {!manager && <small>Diese Mitteilung ist einseitig. Bei organisatorischen Rückfragen bitte die Disposition über den vorgesehenen Kontaktweg erreichen.</small>}
            </div>
          ) : <Empty>Mitteilung auswählen.</Empty>}
        </div>
      </div>

      {manager && <FormModal open={modal} title="Neue Mitteilung" onClose={() => setModal(false)} onSave={sendAnnouncement} busy={busy} saveLabel="Versenden">
        <IonInput fill="outline" label="Titel" labelPlacement="floating" value={form.title} onIonInput={(event) => setForm({ ...form, title: value(event) })} />
        <IonTextarea fill="outline" autoGrow label="Text" labelPlacement="floating" value={form.body} onIonInput={(event) => setForm({ ...form, body: value(event) })} />
        <label className="field-check">Alle Mitarbeiter & Kunden <IonToggle checked={!!form.all_recipients} onIonChange={(event) => setForm({ ...form, all_recipients: event.detail.checked })} /></label>
        {!form.all_recipients && <IonSelect multiple fill="outline" label="Empfänger" labelPlacement="floating" value={form.recipients} onIonChange={(event) => setForm({ ...form, recipients: value(event) })}>
          {recipientCandidates.map((person: any) => <IonSelectOption value={person.id} key={person.id}>{person.name || person.email} · {person.role === 'worker' ? 'Mitarbeiter' : 'Kunde'}</IonSelectOption>)}
        </IonSelect>}
        <label className="file-field">Bild / Datei (optional, max. 20 MB)<input type="file" accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt" onChange={(event) => setForm({ ...form, attachment: event.target.files?.[0] || null })} /></label>
        <small>Beim Versand wird für jeden Empfänger automatisch eine In-App Notification erstellt und – falls auf dem Gerät eingerichtet – per Push zugestellt.</small>
      </FormModal>}

      <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
    </>
  );
}

function Ranking'''
regex_once('frontend/src/App.tsx', r'function Messages\(\{ user \}: \{ user: User \}\) \{.*?\n\}\n\nfunction Ranking', announcements_component)
replace_once('frontend/src/App.tsx', "else if (view === 'messages') content = <Messages user={user} />;", "else if (view === 'messages') content = <Announcements user={user} />;")

phase6_e2e = '''import { expect, test } from '@playwright/test';\nimport { readFileSync } from 'node:fs';\nimport { resolve } from 'node:path';\n\ntest('Phase 6 exposes per-assignee confirmation status and direct controls in schedule cards', async () => {\n  const source = readFileSync(resolve(process.cwd(), 'src/ScheduleV2.tsx'), 'utf8');\n  expect(source).toContain('confirmation_required');\n  expect(source).toContain("'Ausstehend'");\n  expect(source).toContain("'Bestätigt'");\n  expect(source).toContain("'Abgelehnt'");\n  expect(source).toContain('shift-confirmations');\n  expect(source).toContain('Bestätigen');\n  expect(source).toContain('Ablehnen');\n  expect(source).toContain('confirmation/');\n  expect(source).toContain('Bestätigung durch zugewiesene Mitarbeiter erforderlich');\n});\n\ntest('Phase 6 replaces Chat UI with one-way Mitteilungen, file upload, audience selection and history', async () => {\n  const app = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8');\n  expect(app).toContain('function Announcements');\n  expect(app).toContain("api('announcements/')");\n  expect(app).toContain('all_recipients');\n  expect(app).toContain('recipient_ids');\n  expect(app).toContain('Bild / Datei');\n  expect(app).toContain('Versandhistorie');\n  expect(app).toContain('Push wurde ausgelöst');\n  expect(app).not.toContain("api('conversations/')");\n  expect(app).not.toContain('Neue Unterhaltung');\n  expect(app).not.toContain("messages: 'Chat'");\n});\n'''
path('frontend/e2e/phase6-confirmations-mitteilungen.spec.ts').write_text(phase6_e2e, encoding='utf-8')

print('Phase 6 source patch applied.')

from pathlib import Path


def replace_once(path, old, new):
    file = Path(path)
    text = file.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'Patch target not found in {path}: {old[:120]!r}')
    file.write_text(text.replace(old, new, 1), encoding='utf-8')


# Social login is invitation-only: an OAuth identity may sign into an existing portal
# account, but it may not silently create an unapproved employee account.
replace_once(
    'backend/core/oauth.py',
    """    user,created=User.objects.get_or_create(email=email.lower(),defaults={'username':email.lower(),'first_name':profile.get('given_name',''),'last_name':profile.get('family_name',''),'role':User.Role.WORKER})
    if created: user.set_unusable_password(); user.save()
    refresh=RefreshToken.for_user(user); target=data['target']; separator='&' if '?' in target else '?'
""",
    """    try:
        user=User.objects.get(email=email.lower())
    except User.DoesNotExist as exc:
        raise ValueError('Für diese E-Mail-Adresse wurde noch kein Portalzugang durch die Administration angelegt.') from exc
    if not user.is_active:
        raise ValueError('Dieser Portalzugang ist deaktiviert.')
    changed=[]
    if not user.first_name and profile.get('given_name'):
        user.first_name=profile.get('given_name',''); changed.append('first_name')
    if not user.last_name and profile.get('family_name'):
        user.last_name=profile.get('family_name',''); changed.append('last_name')
    if changed: user.save(update_fields=changed)
    refresh=RefreshToken.for_user(user); target=data['target']; separator='&' if '?' in target else '?'
""",
)

# Backend permission and geofence helpers.
replace_once(
    'backend/core/views.py',
    "import secrets\nfrom datetime import timedelta",
    "import secrets\nfrom math import asin, cos, radians, sin, sqrt\nfrom datetime import timedelta",
)
replace_once(
    'backend/core/views.py',
    "from rest_framework.response import Response",
    "from rest_framework.response import Response\nfrom rest_framework.exceptions import ValidationError",
)
replace_once(
    'backend/core/views.py',
    """def create_worker_account(data):
""",
    """def ensure_worker_assignable(worker, starts_at, ends_at, exclude_shift=None):
    if not worker:
        return
    overlaps = Shift.objects.filter(
        worker=worker,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    ).exclude(status=Shift.Status.CANCELLED)
    if exclude_shift:
        overlaps = overlaps.exclude(pk=exclude_shift)
    if overlaps.exists():
        raise ValidationError('Der Mitarbeiter hat in diesem Zeitraum bereits eine Schicht.')
    if Availability.objects.filter(
        worker=worker,
        available=False,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    ).exists():
        raise ValidationError('Der Mitarbeiter ist in diesem Zeitraum nicht verfügbar.')


def geofence_error(shift, lat, lng):
    if not shift or shift.location.latitude is None or shift.location.longitude is None:
        return None
    if lat in (None, '') or lng in (None, ''):
        return 'Für diesen Einsatz ist die Standortfreigabe erforderlich.'
    try:
        lat1, lon1 = radians(float(lat)), radians(float(lng))
        lat2, lon2 = radians(float(shift.location.latitude)), radians(float(shift.location.longitude))
    except (TypeError, ValueError):
        return 'Die übermittelten Standortdaten sind ungültig.'
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    distance = 6371000 * 2 * asin(sqrt(value))
    if distance > shift.location.geofence_radius_m:
        return f'Du befindest dich {round(distance)} m vom Einsatzort entfernt. Erlaubt sind {shift.location.geofence_radius_m} m.'
    return None


def create_worker_account(data):
""",
)
replace_once(
    'backend/core/views.py',
    """            vat_id=str(data.get('vat_id', '')).strip(),
            notes=str(data.get('notes', '')).strip(),
""",
    """            vat_id=str(data.get('vat_id', '')).strip(),
            contract_visibility_enabled=data.get('contract_visibility_enabled', True) not in (False, 'false', '0', 0),
            notes=str(data.get('notes', '')).strip(),
""",
)
replace_once(
    'backend/core/views.py',
    """class UserViewSet(viewsets.ReadOnlyModelViewSet):
""",
    """class ManagerMutationMixin:
    manager_mutations = {'create', 'update', 'partial_update', 'destroy'}

    def get_permissions(self):
        if getattr(self, 'action', None) in self.manager_mutations:
            return [IsAdminOrManager()]
        return super().get_permissions()


class UserViewSet(viewsets.ReadOnlyModelViewSet):
""",
)
for name in [
    'ClientCompanyViewSet',
    'WorkerViewSet',
    'LocationViewSet',
    'PositionViewSet',
    'AvailabilityViewSet',
    'ShiftViewSet',
    'TimeEntryViewSet',
    'ShiftSwapViewSet',
    'ContractViewSet',
    'PayrollViewSet',
]:
    replace_once(
        'backend/core/views.py',
        f'class {name}(BaseModelViewSet):',
        f'class {name}(ManagerMutationMixin, BaseModelViewSet):',
    )

# A worker may create a time-off request, but cannot modify its decision fields.
replace_once(
    'backend/core/views.py',
    """class TimeOffViewSet(BaseModelViewSet):
    queryset = TimeOffRequest.objects.select_related('worker__user').all()
""",
    """class TimeOffViewSet(BaseModelViewSet):
    queryset = TimeOffRequest.objects.select_related('worker__user').all()
""",
)
replace_once(
    'backend/core/views.py',
    """    def get_queryset(self):
        return scoped(self.queryset, self.request.user)

    def perform_create(self, serializer):
        values = {}
""",
    """    def get_queryset(self):
        return scoped(self.queryset, self.request.user)

    def get_permissions(self):
        if getattr(self, 'action', None) in {'update', 'partial_update', 'destroy'}:
            return [IsAdminOrManager()]
        return super().get_permissions()

    def perform_create(self, serializer):
        values = {}
""",
)

# Only managers can alter or delete documents after upload; worker/client uploads
# remain forced into their own digital folder by perform_create.
replace_once(
    'backend/core/views.py',
    """class DocumentViewSet(BaseModelViewSet):
    queryset = Document.objects.select_related('worker__user', 'client').all()
""",
    """class DocumentViewSet(BaseModelViewSet):
    queryset = Document.objects.select_related('worker__user', 'client').all()

    def get_permissions(self):
        if getattr(self, 'action', None) in {'update', 'partial_update', 'destroy'}:
            return [IsAdminOrManager()]
        return super().get_permissions()
""",
)

# Ratings may be submitted by a client or manager, but only managers may edit/delete.
replace_once(
    'backend/core/views.py',
    """class RatingViewSet(BaseModelViewSet):
    queryset = WorkerRating.objects.select_related('worker__user', 'client', 'shift').all()
""",
    """class RatingViewSet(BaseModelViewSet):
    queryset = WorkerRating.objects.select_related('worker__user', 'client', 'shift').all()

    def get_permissions(self):
        if getattr(self, 'action', None) in {'update', 'partial_update', 'destroy'}:
            return [IsAdminOrManager()]
        return super().get_permissions()
""",
)
replace_once(
    'backend/core/views.py',
    """    def perform_create(self, serializer):
        values = {'created_by': self.request.user}
        if self.request.user.role == 'client':
""",
    """    def perform_create(self, serializer):
        if self.request.user.role not in {'client', 'admin', 'manager'}:
            raise ValidationError('Nur Kunden oder die Administration dürfen Bewertungen abgeben.')
        values = {'created_by': self.request.user}
        if self.request.user.role == 'client':
""",
)

# Validate direct assignment during shift creation, not only later drag/drop assignment.
replace_once(
    'backend/core/views.py',
    """    def get_queryset(self):
        user = self.request.user
        if user.role in {'admin', 'manager'}:
            return self.queryset
        if user.role == 'worker':
            return self.queryset.filter(Q(worker__user=user) | Q(is_open=True, status=Shift.Status.PUBLISHED)).distinct()
        return self.queryset.filter(client__contacts=user)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
""",
    """    def get_queryset(self):
        user = self.request.user
        if user.role in {'admin', 'manager'}:
            return self.queryset
        if user.role == 'worker':
            return self.queryset.filter(Q(worker__user=user) | Q(is_open=True, status=Shift.Status.PUBLISHED)).distinct()
        return self.queryset.filter(client__contacts=user)

    def perform_create(self, serializer):
        worker = serializer.validated_data.get('worker')
        starts_at = serializer.validated_data.get('starts_at')
        ends_at = serializer.validated_data.get('ends_at')
        ensure_worker_assignable(worker, starts_at, ends_at)
        obj = serializer.save()
        if worker:
            Notification.objects.create(
                user=worker.user,
                kind=f'shift-assigned-{obj.id}',
                title='Neue Schicht zugeteilt',
                body=f'{obj.starts_at:%d.%m.%Y %H:%M} – {obj.location.name}',
                action_url='/schedule',
            )
        audit(self.request, 'shift.created', obj)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
""",
)

# Replace duplicated checks with the shared validator and return a clean API error.
replace_once(
    'backend/core/views.py',
    """        if worker:
            if Shift.objects.filter(
                worker=worker,
                starts_at__lt=shift.ends_at,
                ends_at__gt=shift.starts_at,
            ).exclude(pk=shift.pk).exclude(status=Shift.Status.CANCELLED).exists():
                return Response({'detail': 'Der Mitarbeiter hat in diesem Zeitraum bereits eine Schicht.'}, status=400)
            if Availability.objects.filter(
                worker=worker,
                available=False,
                starts_at__lt=shift.ends_at,
                ends_at__gt=shift.starts_at,
            ).exists():
                return Response({'detail': 'Der Mitarbeiter ist in diesem Zeitraum nicht verfügbar.'}, status=400)
""",
    """        if worker:
            try:
                ensure_worker_assignable(worker, shift.starts_at, shift.ends_at, shift.pk)
            except ValidationError as exc:
                return Response({'detail': str(exc.detail[0])}, status=400)
""",
)
replace_once(
    'backend/core/views.py',
    """        if Shift.objects.filter(
            worker=worker,
            starts_at__lt=shift.ends_at,
            ends_at__gt=shift.starts_at,
        ).exclude(pk=shift.pk).exclude(status=Shift.Status.CANCELLED).exists():
            return Response({'detail': 'Du hast in diesem Zeitraum bereits eine Schicht.'}, status=400)
        if Availability.objects.filter(
            worker=worker,
            available=False,
            starts_at__lt=shift.ends_at,
            ends_at__gt=shift.starts_at,
        ).exists():
            return Response({'detail': 'Du bist für diesen Zeitraum als nicht verfügbar eingetragen.'}, status=400)
""",
    """        try:
            ensure_worker_assignable(worker, shift.starts_at, shift.ends_at, shift.pk)
        except ValidationError as exc:
            return Response({'detail': str(exc.detail[0])}, status=400)
""",
)

# GPS clocking automatically associates the current assigned shift and enforces the
# configured location geofence whenever coordinates exist for the Einsatzort.
replace_once(
    'backend/core/views.py',
    """    @action(detail=False, methods=['post'])
    def clock_in(self, request):
        worker = request.user.worker_profile
        if TimeEntry.objects.filter(worker=worker, clock_out__isnull=True).exists():
            return Response({'detail': 'Du bist bereits eingestempelt.'}, status=400)
        entry = TimeEntry.objects.create(
            worker=worker,
            shift_id=request.data.get('shift'),
            clock_in=timezone.now(),
            clock_in_lat=request.data.get('lat'),
            clock_in_lng=request.data.get('lng'),
        )
""",
    """    @action(detail=False, methods=['post'])
    def clock_in(self, request):
        if request.user.role != 'worker':
            return Response({'detail': 'Zeiterfassung ist nur im Mitarbeiterportal möglich.'}, status=403)
        worker = request.user.worker_profile
        if TimeEntry.objects.filter(worker=worker, clock_out__isnull=True).exists():
            return Response({'detail': 'Du bist bereits eingestempelt.'}, status=400)
        now = timezone.now()
        shift = None
        if request.data.get('shift'):
            shift = Shift.objects.filter(pk=request.data.get('shift'), worker=worker).select_related('location').first()
            if not shift:
                return Response({'detail': 'Die ausgewählte Schicht gehört nicht zu deinem Profil.'}, status=403)
        else:
            shift = Shift.objects.filter(
                worker=worker,
                starts_at__lte=now + timedelta(hours=4),
                ends_at__gte=now - timedelta(hours=4),
                status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
            ).select_related('location').order_by('starts_at').first()
        error = geofence_error(shift, request.data.get('lat'), request.data.get('lng'))
        if error:
            return Response({'detail': error}, status=400)
        entry = TimeEntry.objects.create(
            worker=worker,
            shift=shift,
            clock_in=now,
            clock_in_lat=request.data.get('lat'),
            clock_in_lng=request.data.get('lng'),
        )
""",
)
replace_once(
    'backend/core/views.py',
    """        entry.clock_out = timezone.now()
        entry.clock_out_lat = request.data.get('lat')
        entry.clock_out_lng = request.data.get('lng')
""",
    """        if entry.shift_id:
            entry.shift = Shift.objects.select_related('location').get(pk=entry.shift_id)
        error = geofence_error(entry.shift, request.data.get('lat'), request.data.get('lng'))
        if error:
            return Response({'detail': error}, status=400)
        entry.clock_out = timezone.now()
        entry.clock_out_lat = request.data.get('lat')
        entry.clock_out_lng = request.data.get('lng')
""",
)

# Avoid committing an approved swap before a target worker has been selected.
replace_once(
    'backend/core/advanced_views.py',
    """        with transaction.atomic():
            obj.status = decision
            obj.save(update_fields=['status'])
            if decision == ShiftSwapRequest.Status.APPROVED:
                if not obj.offered_to_id:
                    return Response({'detail': 'Für die Freigabe muss ein Zielmitarbeiter ausgewählt sein.'}, status=400)
                overlap = Shift.objects.filter(
""",
    """        if decision == ShiftSwapRequest.Status.APPROVED and not obj.offered_to_id:
            return Response({'detail': 'Für die Freigabe muss ein Zielmitarbeiter ausgewählt sein.'}, status=400)
        with transaction.atomic():
            if decision == ShiftSwapRequest.Status.APPROVED:
                overlap = Shift.objects.filter(
""",
)
replace_once(
    'backend/core/advanced_views.py',
    """                obj.shift.save(update_fields=['worker', 'is_open', 'status'])
    else:
""",
    """                obj.shift.save(update_fields=['worker', 'is_open', 'status'])
            obj.status = decision
            obj.save(update_fields=['status'])
    else:
""",
)

# Complete the requested contract fields and allow both employee and client portals
# to sign the contract assigned to them.
replace_once(
    'frontend/src/App.tsx',
    "employment_type: worker?.employment_type || '',",
    "employment_type: form.employment_type || worker?.employment_type || '',",
)
replace_once(
    'frontend/src/App.tsx',
    "{user.role === 'client' && ['ready', 'sent'].includes(contract.status) && (",
    "{['client', 'worker'].includes(user.role) && ['ready', 'sent'].includes(contract.status) && (",
)
replace_once(
    'frontend/src/App.tsx',
    """        <div className="form-divider">Variablen für das Grundmuster</div>
        <IonInput
          fill="outline"
          label="Einsatzbereich"
""",
    """        <div className="form-divider">Variablen für das Grundmuster</div>
        <IonItem lines="none" className="toggle-field">
          <IonLabel>Neuanstellung</IonLabel>
          <IonToggle checked={form.neuanstellung !== false} onIonChange={(event) => setForm({ ...form, neuanstellung: event.detail.checked })} />
        </IonItem>
        <IonSelect fill="outline" label="Arbeitszeit / Beschäftigungsart" labelPlacement="floating" value={form.employment_type} onIonChange={(event) => setForm({ ...form, employment_type: value(event) })}>
          <IonSelectOption value="minijob">Minijob</IonSelectOption>
          <IonSelectOption value="teilzeit">Teilzeit</IonSelectOption>
          <IonSelectOption value="vollzeit">Vollzeit</IonSelectOption>
          <IonSelectOption value="student">Studentische Aushilfe</IonSelectOption>
        </IonSelect>
        <IonInput
          fill="outline"
          label="1b Einsatzbereich"
""",
)
replace_once(
    'frontend/src/App.tsx',
    "label=\"Zulage (€)\"",
    "label=\"Übertarifliche Zulage (€)\"",
)

# Client contract visibility is configurable at onboarding.
replace_once(
    'frontend/src/App.tsx',
    "onSave={() => submit('clients/onboard/', clientForm, () => setClientForm({}))}",
    "onSave={() => submit('clients/onboard/', clientForm, () => setClientForm({ contract_visibility_enabled: true }))}",
)
replace_once(
    'frontend/src/App.tsx',
    """        <div className="form-divider">Portal-Zugang für Ansprechpartner</div>
        <IonInput
""",
    """        <IonItem lines="none" className="toggle-field">
          <IonLabel>Vertragsunterlagen im Kundenportal sichtbar</IonLabel>
          <IonToggle checked={clientForm.contract_visibility_enabled !== false} onIonChange={(event) => setClientForm({ ...clientForm, contract_visibility_enabled: event.detail.checked })} />
        </IonItem>
        <div className="form-divider">Portal-Zugang für Ansprechpartner</div>
        <IonInput
""",
)

print('Final workforce security and workflow hardening patches applied.')

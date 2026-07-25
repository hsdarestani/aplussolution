import csv
import io
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Avg, Sum, Q
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import *
from .serializers import *
from .permissions import IsAdminOrManager
from .services import audit, render_contract_pdf, sign_contract
from . import oauth


def scoped(qs, user, worker_field='worker', client_field='client'):
    if user.role in {'admin', 'manager'}:
        return qs
    if user.role == 'worker':
        return qs.filter(**{f'{worker_field}__user': user})
    if user.role == 'client':
        return qs.filter(**{f'{client_field}__contacts': user})
    return qs.none()


def generated_password():
    return secrets.token_urlsafe(12)


def next_number(model, field, prefix):
    number = model.objects.count() + 1
    candidate = f'{prefix}-{number:04d}'
    while model.objects.filter(**{field: candidate}).exists():
        number += 1
        candidate = f'{prefix}-{number:04d}'
    return candidate


def create_worker_account(data):
    email = str(data.get('email', '')).strip().lower()
    if not email:
        raise ValueError('E-Mail-Adresse ist erforderlich.')
    if User.objects.filter(email=email).exists():
        raise ValueError('Diese E-Mail-Adresse ist bereits registriert.')
    password = str(data.get('password') or generated_password())
    employee_number = str(data.get('employee_number') or next_number(WorkerProfile, 'employee_number', 'MA'))
    with transaction.atomic():
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=str(data.get('first_name', '')).strip(),
            last_name=str(data.get('last_name', '')).strip(),
            phone=str(data.get('phone', '')).strip(),
            role=User.Role.WORKER,
            is_onboarded=True,
        )
        worker = WorkerProfile.objects.create(
            user=user,
            employee_number=employee_number,
            employment_type=data.get('employment_type') or WorkerProfile.EmploymentType.MINI,
            monthly_hours=data.get('monthly_hours') or None,
            tariff_hourly_rate=data.get('tariff_hourly_rate') or None,
            extra_allowance=data.get('extra_allowance') or 0,
            skills=data.get('skills') or [],
        )
    return worker, password


def create_client_account(data):
    name = str(data.get('name', '')).strip()
    if not name:
        raise ValueError('Firmenname ist erforderlich.')
    customer_number = str(data.get('customer_number') or next_number(ClientCompany, 'customer_number', 'KD'))
    if ClientCompany.objects.filter(customer_number=customer_number).exists():
        raise ValueError('Diese Kundennummer ist bereits vorhanden.')
    contact_email = str(data.get('contact_email', '')).strip().lower()
    password = None
    with transaction.atomic():
        client = ClientCompany.objects.create(
            name=name,
            customer_number=customer_number,
            address=str(data.get('address', '')).strip(),
            vat_id=str(data.get('vat_id', '')).strip(),
            notes=str(data.get('notes', '')).strip(),
        )
        if contact_email:
            if User.objects.filter(email=contact_email).exists():
                raise ValueError('Die Kontakt-E-Mail ist bereits registriert.')
            password = str(data.get('password') or generated_password())
            contact = User.objects.create_user(
                email=contact_email,
                password=password,
                first_name=str(data.get('contact_first_name', '')).strip(),
                last_name=str(data.get('contact_last_name', '')).strip(),
                phone=str(data.get('contact_phone', '')).strip(),
                role=User.Role.CLIENT,
                is_onboarded=True,
            )
            client.contacts.add(contact)
    return client, password


def parse_csv_file(upload):
    raw = upload.read().decode('utf-8-sig')
    sample = raw[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;')
    except csv.Error:
        dialect = csv.excel
    return list(csv.DictReader(io.StringIO(raw), dialect=dialect))


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    user = authenticate(
        request,
        username=request.data.get('email', '').lower(),
        password=request.data.get('password'),
    )
    if not user:
        return Response({'detail': 'E-Mail oder Passwort ist falsch.'}, status=400)
    refresh = RefreshToken.for_user(user)
    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': UserSerializer(user, context={'request': request}).data,
    })


@api_view(['GET'])
def me(request):
    return Response(UserSerializer(request.user, context={'request': request}).data)


@api_view(['POST'])
def change_password(request):
    current = request.data.get('current_password', '')
    new_password = request.data.get('new_password', '')
    if len(new_password) < 10:
        return Response({'detail': 'Das neue Passwort muss mindestens 10 Zeichen lang sein.'}, status=400)
    if not request.user.check_password(current):
        return Response({'detail': 'Das aktuelle Passwort ist falsch.'}, status=400)
    request.user.set_password(new_password)
    request.user.save(update_fields=['password'])
    audit(request, 'account.password_changed', request.user)
    return Response({'detail': 'Passwort wurde geändert. Bitte erneut anmelden.'})


@api_view(['POST'])
def request_account_deletion(request):
    request.user.deletion_requested_at = timezone.now()
    request.user.save(update_fields=['deletion_requested_at'])
    audit(request, 'account.deletion_requested', request.user)
    return Response({'detail': 'Deine Löschanfrage wurde erfasst. Gesetzlich aufzubewahrende Unterlagen werden gemäß Datenschutzinformation behandelt.'})


@api_view(['GET'])
@permission_classes([AllowAny])
def oauth_start(request, provider):
    target = request.GET.get('target') or settings.APP_URL + '/auth/callback'
    return HttpResponseRedirect(oauth.start(provider, target))


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def oauth_callback(request, provider):
    code = request.data.get('code') or request.GET.get('code')
    state_value = request.data.get('state') or request.GET.get('state')
    try:
        return HttpResponseRedirect(oauth.finish(provider, code, state_value))
    except Exception as exc:
        return HttpResponseRedirect(settings.APP_URL + '/login?error=' + str(exc))


class BaseModelViewSet(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, f'{obj.__class__.__name__.lower()}.created', obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, f'{obj.__class__.__name__.lower()}.updated', obj)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'email')
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdminOrManager]


class ClientCompanyViewSet(BaseModelViewSet):
    queryset = ClientCompany.objects.prefetch_related('contacts').all()
    serializer_class = ClientCompanySerializer
    search_fields = ['name', 'customer_number']

    def get_queryset(self):
        return self.queryset if self.request.user.role in {'admin', 'manager'} else self.queryset.filter(contacts=self.request.user)

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrManager])
    def onboard(self, request):
        try:
            client, password = create_client_account(request.data)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        audit(request, 'client.onboarded', client)
        return Response({
            'client': self.get_serializer(client).data,
            'temporary_password': password,
        }, status=201)

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrManager])
    def import_csv(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'CSV-Datei fehlt.'}, status=400)
        created, errors, credentials = 0, [], []
        for index, row in enumerate(parse_csv_file(upload), start=2):
            try:
                client, password = create_client_account(row)
                created += 1
                if password:
                    credentials.append({'email': row.get('contact_email'), 'password': password})
            except Exception as exc:
                errors.append({'line': index, 'error': str(exc)})
        return Response({'created': created, 'errors': errors, 'credentials': credentials})

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def archive(self, request, pk=None):
        client = self.get_object()
        client.active = False
        client.save(update_fields=['active'])
        audit(request, 'client.archived', client)
        return Response(self.get_serializer(client).data)


class WorkerViewSet(BaseModelViewSet):
    queryset = WorkerProfile.objects.select_related('user').all()
    serializer_class = WorkerProfileSerializer
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'employee_number']

    def get_queryset(self):
        return self.queryset if self.request.user.role in {'admin', 'manager'} else self.queryset.filter(user=self.request.user)

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrManager])
    def onboard(self, request):
        try:
            worker, password = create_worker_account(request.data)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        audit(request, 'worker.onboarded', worker)
        return Response({
            'worker': self.get_serializer(worker).data,
            'temporary_password': password,
        }, status=201)

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrManager])
    def import_csv(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'CSV-Datei fehlt.'}, status=400)
        created, errors, credentials = 0, [], []
        for index, row in enumerate(parse_csv_file(upload), start=2):
            try:
                worker, password = create_worker_account(row)
                created += 1
                credentials.append({'email': row.get('email'), 'password': password})
            except Exception as exc:
                errors.append({'line': index, 'error': str(exc)})
        return Response({'created': created, 'errors': errors, 'credentials': credentials})

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def archive(self, request, pk=None):
        worker = self.get_object()
        worker.active = False
        worker.user.is_active = False
        worker.save(update_fields=['active'])
        worker.user.save(update_fields=['is_active'])
        audit(request, 'worker.archived', worker)
        return Response(self.get_serializer(worker).data)


class LocationViewSet(BaseModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer

    def get_queryset(self):
        return self.queryset if self.request.user.role in {'admin', 'manager', 'worker'} else self.queryset.filter(client__contacts=self.request.user)


class PositionViewSet(BaseModelViewSet):
    queryset = Position.objects.all()
    serializer_class = PositionSerializer


class OrderViewSet(BaseModelViewSet):
    queryset = ClientOrder.objects.select_related('client', 'location').all()
    serializer_class = ClientOrderSerializer
    filterset_fields = ['status', 'client']

    def get_queryset(self):
        return self.queryset if self.request.user.role in {'admin', 'manager'} else self.queryset.filter(client__contacts=self.request.user)

    def perform_create(self, serializer):
        values = {'created_by': self.request.user}
        if self.request.user.role == 'client':
            values['client'] = self.request.user.client_companies.first()
        obj = serializer.save(**values)
        audit(self.request, 'order.created', obj)


class AvailabilityViewSet(BaseModelViewSet):
    queryset = Availability.objects.all()
    serializer_class = AvailabilitySerializer

    def get_queryset(self):
        return scoped(self.queryset, self.request.user, worker_field='worker', client_field='worker__user__client_companies')


class ShiftViewSet(BaseModelViewSet):
    queryset = Shift.objects.select_related('worker__user', 'client', 'location', 'position').all()
    serializer_class = ShiftSerializer
    filterset_fields = ['status', 'client', 'worker', 'location', 'is_open']
    ordering_fields = ['starts_at', 'ends_at']

    def get_queryset(self):
        user = self.request.user
        if user.role in {'admin', 'manager'}:
            return self.queryset
        if user.role == 'worker':
            return self.queryset.filter(Q(worker__user=user) | Q(is_open=True, status=Shift.Status.PUBLISHED)).distinct()
        return self.queryset.filter(client__contacts=user)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def publish(self, request, pk=None):
        shift = self.get_object()
        shift.status = Shift.Status.PUBLISHED
        shift.published_at = timezone.now()
        shift.save()
        audit(request, 'shift.published', shift)
        return Response(self.get_serializer(shift).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def assign(self, request, pk=None):
        shift = self.get_object()
        worker_id = request.data.get('worker')
        shift.worker = WorkerProfile.objects.get(pk=worker_id) if worker_id else None
        shift.is_open = not bool(worker_id)
        shift.status = Shift.Status.CONFIRMED if worker_id else Shift.Status.PUBLISHED
        shift.save()
        audit(request, 'shift.assigned', shift, {'worker': worker_id})
        return Response(self.get_serializer(shift).data)

    @action(detail=True, methods=['post'])
    def claim(self, request, pk=None):
        shift = self.get_object()
        if request.user.role != 'worker' or not shift.is_open:
            return Response({'detail': 'Diese Schicht kann nicht übernommen werden.'}, status=400)
        shift.worker = request.user.worker_profile
        shift.is_open = False
        shift.status = Shift.Status.CONFIRMED
        shift.save()
        audit(request, 'shift.claimed', shift)
        return Response(self.get_serializer(shift).data)


class TimeEntryViewSet(BaseModelViewSet):
    queryset = TimeEntry.objects.select_related('worker__user', 'shift').all()
    serializer_class = TimeEntrySerializer
    filterset_fields = ['worker', 'approved']

    def get_queryset(self):
        return scoped(self.queryset, self.request.user)

    @action(detail=False, methods=['post'])
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
        audit(request, 'time.clock_in', entry)
        return Response(self.get_serializer(entry).data, status=201)

    @action(detail=False, methods=['post'])
    def clock_out(self, request):
        entry = TimeEntry.objects.filter(worker=request.user.worker_profile, clock_out__isnull=True).order_by('-clock_in').first()
        if not entry:
            return Response({'detail': 'Keine laufende Zeiterfassung gefunden.'}, status=400)
        entry.clock_out = timezone.now()
        entry.clock_out_lat = request.data.get('lat')
        entry.clock_out_lng = request.data.get('lng')
        entry.save()
        audit(request, 'time.clock_out', entry)
        return Response(self.get_serializer(entry).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def approve(self, request, pk=None):
        entry = self.get_object()
        entry.approved = True
        entry.approved_by = request.user
        entry.save()
        audit(request, 'time.approved', entry)
        return Response(self.get_serializer(entry).data)


class TimeOffViewSet(BaseModelViewSet):
    queryset = TimeOffRequest.objects.select_related('worker__user').all()
    serializer_class = TimeOffRequestSerializer
    filterset_fields = ['status', 'worker']

    def get_queryset(self):
        return scoped(self.queryset, self.request.user)

    def perform_create(self, serializer):
        values = {}
        if self.request.user.role == 'worker':
            values['worker'] = self.request.user.worker_profile
        obj = serializer.save(**values)
        audit(self.request, 'timeoff.created', obj)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def decide(self, request, pk=None):
        obj = self.get_object()
        decision = request.data.get('status')
        if decision not in {'approved', 'rejected'}:
            return Response({'detail': 'Ungültige Entscheidung.'}, status=400)
        obj.status = decision
        obj.decided_by = request.user
        obj.save()
        audit(request, 'timeoff.decided', obj, {'status': decision})
        return Response(self.get_serializer(obj).data)


class ShiftSwapViewSet(BaseModelViewSet):
    queryset = ShiftSwapRequest.objects.all()
    serializer_class = ShiftSwapRequestSerializer

    def get_queryset(self):
        if self.request.user.role in {'admin', 'manager'}:
            return self.queryset
        return self.queryset.filter(Q(requested_by__user=self.request.user) | Q(offered_to__user=self.request.user))


class ContractTemplateViewSet(BaseModelViewSet):
    queryset = ContractTemplate.objects.all()
    serializer_class = ContractTemplateSerializer
    permission_classes = [IsAdminOrManager]


class ContractViewSet(BaseModelViewSet):
    queryset = Contract.objects.select_related('template', 'worker__user', 'client').all()
    serializer_class = ContractSerializer
    filterset_fields = ['status', 'template__kind', 'worker', 'client']

    def get_queryset(self):
        user = self.request.user
        if user.role in {'admin', 'manager'}:
            return self.queryset
        if user.role == 'worker':
            return self.queryset.filter(worker__user=user)
        return self.queryset.filter(client__contacts=user, client__contract_visibility_enabled=True)

    def perform_create(self, serializer):
        obj = serializer.save(created_by=self.request.user)
        audit(self.request, 'contract.created', obj)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def generate_pdf(self, request, pk=None):
        contract = self.get_object()
        contract.pdf.save(f'{contract.id}.pdf', render_contract_pdf(contract))
        contract.status = Contract.Status.READY
        contract.save()
        audit(request, 'contract.pdf_generated', contract)
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def send(self, request, pk=None):
        contract = self.get_object()
        if not contract.pdf:
            contract.pdf.save(f'{contract.id}.pdf', render_contract_pdf(contract))
        contract.status = Contract.Status.SENT
        contract.sent_at = timezone.now()
        contract.save()
        audit(request, 'contract.sent', contract)
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        contract = self.get_object()
        if contract.status not in {Contract.Status.READY, Contract.Status.SENT}:
            return Response({'detail': 'Der Vertrag kann aktuell nicht unterzeichnet werden.'}, status=400)
        sign_contract(contract, request.data.get('name', '').strip(), request.data.get('signature', ''), request)
        return Response(self.get_serializer(contract).data)


class DocumentViewSet(BaseModelViewSet):
    queryset = Document.objects.select_related('worker__user', 'client').all()
    serializer_class = DocumentSerializer
    filterset_fields = ['folder', 'worker', 'client']

    def get_queryset(self):
        user = self.request.user
        if user.role in {'admin', 'manager'}:
            return self.queryset
        if user.role == 'worker':
            return self.queryset.filter(worker__user=user).exclude(visibility=Document.Visibility.ADMIN)
        return self.queryset.filter(client__contacts=user, visibility__in=[Document.Visibility.CLIENT, Document.Visibility.SHARED])

    def perform_create(self, serializer):
        values = {'uploaded_by': self.request.user}
        if self.request.user.role == 'worker':
            values['worker'] = self.request.user.worker_profile
        if self.request.user.role == 'client':
            values['client'] = self.request.user.client_companies.first()
        obj = serializer.save(**values)
        audit(self.request, 'document.uploaded', obj)


class PayrollViewSet(BaseModelViewSet):
    queryset = PayrollStatement.objects.select_related('worker__user').all()
    serializer_class = PayrollStatementSerializer

    def get_queryset(self):
        return scoped(self.queryset, self.request.user)


class RatingViewSet(BaseModelViewSet):
    queryset = WorkerRating.objects.select_related('worker__user', 'client', 'shift').all()
    serializer_class = WorkerRatingSerializer

    def get_queryset(self):
        if self.request.user.role in {'admin', 'manager'}:
            return self.queryset
        if self.request.user.role == 'worker':
            return self.queryset.filter(worker__user=self.request.user)
        return self.queryset.filter(client__contacts=self.request.user)

    def perform_create(self, serializer):
        values = {'created_by': self.request.user}
        if self.request.user.role == 'client':
            values['client'] = self.request.user.client_companies.first()
        obj = serializer.save(**values)
        obj.worker.ranking_points += obj.score * 10
        obj.worker.save(update_fields=['ranking_points'])
        audit(self.request, 'rating.created', obj)


class ConversationViewSet(BaseModelViewSet):
    queryset = Conversation.objects.prefetch_related('participants', 'messages__sender').all()
    serializer_class = ConversationSerializer

    def get_queryset(self):
        return self.queryset if self.request.user.role in {'admin', 'manager'} else self.queryset.filter(participants=self.request.user)

    def perform_create(self, serializer):
        conversation = serializer.save()
        conversation.participants.add(self.request.user)
        audit(self.request, 'conversation.created', conversation)

    @action(detail=True, methods=['post'])
    def post_message(self, request, pk=None):
        conversation = self.get_object()
        body = str(request.data.get('body', '')).strip()
        if not body:
            return Response({'detail': 'Nachricht darf nicht leer sein.'}, status=400)
        message = Message.objects.create(conversation=conversation, sender=request.user, body=body)
        return Response(MessageSerializer(message, context={'request': request}).data, status=201)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        obj = self.get_object()
        obj.read_at = timezone.now()
        obj.save()
        return Response(self.get_serializer(obj).data)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def setup_demo(request):
    now = timezone.now()
    credentials = []
    with transaction.atomic():
        client, _ = ClientCompany.objects.get_or_create(
            customer_number='KD-DEMO',
            defaults={
                'name': 'A+ Demo Kunde',
                'address': 'Musterstraße 24, 60311 Frankfurt am Main',
                'notes': 'Demodatensatz – kann später archiviert werden.',
            },
        )
        location, _ = Location.objects.get_or_create(
            client=client,
            name='City Event Frankfurt',
            defaults={'address': 'Messeplatz 1, 60327 Frankfurt am Main'},
        )
        position, _ = Position.objects.get_or_create(name='Servicekraft')
        workers = []
        for index, name in enumerate([('Anna', 'Becker'), ('Lukas', 'Schmidt'), ('Mia', 'Wagner')], start=1):
            email = f'demo.worker{index}@aplus-solution.de'
            user = User.objects.filter(email=email).first()
            if not user:
                password = generated_password()
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=name[0],
                    last_name=name[1],
                    role=User.Role.WORKER,
                    is_onboarded=True,
                )
                credentials.append({'email': email, 'password': password})
            worker, _ = WorkerProfile.objects.get_or_create(
                user=user,
                defaults={
                    'employee_number': f'DEMO-{index:03d}',
                    'employment_type': WorkerProfile.EmploymentType.MINI,
                    'tariff_hourly_rate': 14.50,
                },
            )
            workers.append(worker)
        order, _ = ClientOrder.objects.get_or_create(
            client=client,
            title='Sommerempfang Frankfurt',
            starts_at=now + timedelta(days=2),
            ends_at=now + timedelta(days=2, hours=8),
            defaults={
                'location': location,
                'requested_staff': 4,
                'status': ClientOrder.Status.PLANNING,
                'description': 'Empfang, Garderobe und Service.',
                'created_by': request.user,
            },
        )
        for index, worker in enumerate(workers):
            Shift.objects.get_or_create(
                order=order,
                worker=worker,
                starts_at=order.starts_at + timedelta(minutes=index * 15),
                defaults={
                    'client': client,
                    'location': location,
                    'position': position,
                    'ends_at': order.ends_at,
                    'break_minutes': 30,
                    'status': Shift.Status.CONFIRMED,
                },
            )
        Shift.objects.get_or_create(
            order=order,
            worker=None,
            starts_at=order.starts_at,
            defaults={
                'client': client,
                'location': location,
                'position': position,
                'ends_at': order.ends_at,
                'break_minutes': 30,
                'status': Shift.Status.PUBLISHED,
                'is_open': True,
            },
        )
        TimeOffRequest.objects.get_or_create(
            worker=workers[0],
            starts_on=(now + timedelta(days=14)).date(),
            ends_on=(now + timedelta(days=16)).date(),
            defaults={'reason': 'Privater Termin'},
        )
        template = ContractTemplate.objects.filter(kind=ContractTemplate.Kind.EMPLOYMENT, active=True).first()
        if template:
            Contract.objects.get_or_create(
                template=template,
                worker=workers[0],
                title='Arbeitsvertrag – Anna Becker',
                defaults={
                    'starts_on': now.date(),
                    'status': Contract.Status.DRAFT,
                    'variables': {
                        'company_name': 'A+ Solution GmbH',
                        'employee_name': 'Anna Becker',
                        'einsatzbereich': 'Eventservice Rhein-Main',
                        'start_date': now.date().isoformat(),
                        'end_date': '',
                        'neuanstellung': True,
                        'taetigkeit': 'Servicekraft',
                        'employment_type': 'Minijob',
                        'monthly_hours': '40',
                        'tariff_hourly_rate': '14.50',
                        'extra_allowance': '0.00',
                    },
                    'created_by': request.user,
                },
            )
    audit(request, 'setup.demo_created', client)
    return Response({
        'detail': 'Demodaten wurden erstellt.',
        'temporary_credentials': credentials,
    })


@api_view(['GET'])
def dashboard(request):
    user = request.user
    now = timezone.now()
    data = {'role': user.role}
    if user.role in {'admin', 'manager'}:
        data.update({
            'workers': WorkerProfile.objects.filter(active=True).count(),
            'clients': ClientCompany.objects.filter(active=True).count(),
            'open_shifts': Shift.objects.filter(is_open=True, starts_at__gte=now).count(),
            'pending_time_off': TimeOffRequest.objects.filter(status='pending').count(),
            'unapproved_time_entries': TimeEntry.objects.filter(approved=False, clock_out__isnull=False).count(),
            'contracts_due': Contract.objects.filter(
                Q(ends_on__lte=now.date() + timedelta(days=30)) | Q(reminder_date__lte=now.date()),
                status__in=['sent', 'signed', 'ready'],
            ).count(),
            'upcoming_shifts': ShiftSerializer(
                Shift.objects.filter(starts_at__gte=now).order_by('starts_at')[:8],
                many=True,
            ).data,
        })
    elif user.role == 'worker':
        worker = user.worker_profile
        minutes = sum(
            entry.worked_minutes
            for entry in TimeEntry.objects.filter(
                worker=worker,
                clock_in__year=now.year,
                clock_in__month=now.month,
            )
        )
        data.update({
            'worked_minutes': minutes,
            'ranking_points': worker.ranking_points,
            'next_shifts': ShiftSerializer(
                Shift.objects.filter(worker=worker, starts_at__gte=now).order_by('starts_at')[:8],
                many=True,
            ).data,
            'open_shifts': Shift.objects.filter(
                is_open=True,
                status='published',
                starts_at__gte=now,
            ).count(),
        })
    else:
        companies = user.client_companies.all()
        data.update({
            'active_orders': ClientOrder.objects.filter(
                client__in=companies,
                status__in=['new', 'planning', 'confirmed'],
            ).count(),
            'upcoming_shifts': Shift.objects.filter(client__in=companies, starts_at__gte=now).count(),
            'contracts_to_sign': Contract.objects.filter(
                client__in=companies,
                status__in=['ready', 'sent'],
            ).count(),
        })
    return Response(data)

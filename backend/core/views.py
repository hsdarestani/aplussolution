from datetime import timedelta
from django.conf import settings
from django.contrib.auth import authenticate
from django.db.models import Avg, Sum, Q
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from .models import *
from .serializers import *
from .permissions import IsAdminOrManager
from .services import audit, render_contract_pdf, sign_contract
from . import oauth


def scoped(qs, user, worker_field='worker', client_field='client'):
    if user.role in {'admin','manager'}: return qs
    if user.role == 'worker': return qs.filter(**{f'{worker_field}__user': user})
    if user.role == 'client': return qs.filter(**{f'{client_field}__contacts': user})
    return qs.none()


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    user = authenticate(request, username=request.data.get('email','').lower(), password=request.data.get('password'))
    if not user: return Response({'detail':'E-Mail oder Passwort ist falsch.'}, status=400)
    refresh = RefreshToken.for_user(user)
    return Response({'access': str(refresh.access_token), 'refresh': str(refresh), 'user': UserSerializer(user, context={'request':request}).data})

@api_view(['GET'])
def me(request): return Response(UserSerializer(request.user, context={'request': request}).data)

@api_view(['POST'])
def request_account_deletion(request):
    request.user.deletion_requested_at = timezone.now(); request.user.save(update_fields=['deletion_requested_at'])
    audit(request, 'account.deletion_requested', request.user)
    return Response({'detail':'Deine Löschanfrage wurde erfasst. Gesetzlich aufzubewahrende Unterlagen werden gemäß Datenschutzinformation behandelt.'})

@api_view(['GET'])
@permission_classes([AllowAny])
def oauth_start(request, provider):
    target = request.GET.get('target') or settings.APP_URL + '/auth/callback'
    return HttpResponseRedirect(oauth.start(provider, target))

@api_view(['GET','POST'])
@permission_classes([AllowAny])
def oauth_callback(request, provider):
    code = request.data.get('code') or request.GET.get('code'); state_value = request.data.get('state') or request.GET.get('state')
    try: return HttpResponseRedirect(oauth.finish(provider, code, state_value))
    except Exception as exc: return HttpResponseRedirect(settings.APP_URL + '/login?error=' + str(exc))


class BaseModelViewSet(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        obj = serializer.save(); audit(self.request, f'{obj.__class__.__name__.lower()}.created', obj)
    def perform_update(self, serializer):
        obj = serializer.save(); audit(self.request, f'{obj.__class__.__name__.lower()}.updated', obj)

class ClientCompanyViewSet(BaseModelViewSet):
    queryset = ClientCompany.objects.all(); serializer_class = ClientCompanySerializer; search_fields = ['name','customer_number']
    def get_queryset(self):
        return self.queryset if self.request.user.role in {'admin','manager'} else self.queryset.filter(contacts=self.request.user)

class WorkerViewSet(BaseModelViewSet):
    queryset = WorkerProfile.objects.select_related('user').all(); serializer_class = WorkerProfileSerializer; search_fields = ['user__first_name','user__last_name','user__email','employee_number']
    def get_queryset(self):
        return self.queryset if self.request.user.role in {'admin','manager'} else self.queryset.filter(user=self.request.user)

class LocationViewSet(BaseModelViewSet):
    queryset = Location.objects.all(); serializer_class = LocationSerializer
    def get_queryset(self):
        return self.queryset if self.request.user.role in {'admin','manager','worker'} else self.queryset.filter(client__contacts=self.request.user)

class PositionViewSet(BaseModelViewSet): queryset=Position.objects.all(); serializer_class=PositionSerializer

class OrderViewSet(BaseModelViewSet):
    queryset=ClientOrder.objects.select_related('client','location').all(); serializer_class=ClientOrderSerializer; filterset_fields=['status','client']
    def get_queryset(self):
        return self.queryset if self.request.user.role in {'admin','manager'} else self.queryset.filter(client__contacts=self.request.user)
    def perform_create(self, serializer):
        values={'created_by':self.request.user}
        if self.request.user.role=='client': values['client']=self.request.user.client_companies.first()
        obj=serializer.save(**values); audit(self.request,'order.created',obj)

class AvailabilityViewSet(BaseModelViewSet):
    queryset=Availability.objects.all(); serializer_class=AvailabilitySerializer
    def get_queryset(self): return scoped(self.queryset,self.request.user,worker_field='worker',client_field='worker__user__client_companies')

class ShiftViewSet(BaseModelViewSet):
    queryset=Shift.objects.select_related('worker__user','client','location','position').all(); serializer_class=ShiftSerializer
    filterset_fields=['status','client','worker','location','is_open']; ordering_fields=['starts_at','ends_at']
    def get_queryset(self):
        user=self.request.user
        if user.role in {'admin','manager'}: return self.queryset
        if user.role=='worker': return self.queryset.filter(Q(worker__user=user)|Q(is_open=True,status=Shift.Status.PUBLISHED)).distinct()
        return self.queryset.filter(client__contacts=user)
    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def publish(self, request, pk=None):
        shift=self.get_object(); shift.status=Shift.Status.PUBLISHED; shift.published_at=timezone.now(); shift.save(); audit(request,'shift.published',shift); return Response(self.get_serializer(shift).data)
    @action(detail=True, methods=['post'])
    def claim(self, request, pk=None):
        shift=self.get_object()
        if request.user.role!='worker' or not shift.is_open: return Response({'detail':'Diese Schicht kann nicht übernommen werden.'},status=400)
        shift.worker=request.user.worker_profile; shift.is_open=False; shift.status=Shift.Status.CONFIRMED; shift.save(); audit(request,'shift.claimed',shift); return Response(self.get_serializer(shift).data)

class TimeEntryViewSet(BaseModelViewSet):
    queryset=TimeEntry.objects.select_related('worker__user','shift').all(); serializer_class=TimeEntrySerializer; filterset_fields=['worker','approved']
    def get_queryset(self): return scoped(self.queryset,self.request.user)
    @action(detail=False, methods=['post'])
    def clock_in(self, request):
        worker=request.user.worker_profile
        if TimeEntry.objects.filter(worker=worker,clock_out__isnull=True).exists(): return Response({'detail':'Du bist bereits eingestempelt.'},status=400)
        entry=TimeEntry.objects.create(worker=worker,shift_id=request.data.get('shift'),clock_in=timezone.now(),clock_in_lat=request.data.get('lat'),clock_in_lng=request.data.get('lng'))
        audit(request,'time.clock_in',entry); return Response(self.get_serializer(entry).data,status=201)
    @action(detail=False, methods=['post'])
    def clock_out(self, request):
        entry=TimeEntry.objects.filter(worker=request.user.worker_profile,clock_out__isnull=True).order_by('-clock_in').first()
        if not entry: return Response({'detail':'Keine laufende Zeiterfassung gefunden.'},status=400)
        entry.clock_out=timezone.now(); entry.clock_out_lat=request.data.get('lat'); entry.clock_out_lng=request.data.get('lng'); entry.save(); audit(request,'time.clock_out',entry); return Response(self.get_serializer(entry).data)
    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def approve(self, request, pk=None):
        entry=self.get_object(); entry.approved=True; entry.approved_by=request.user; entry.save(); audit(request,'time.approved',entry); return Response(self.get_serializer(entry).data)

class TimeOffViewSet(BaseModelViewSet):
    queryset=TimeOffRequest.objects.all(); serializer_class=TimeOffRequestSerializer; filterset_fields=['status','worker']
    def get_queryset(self): return scoped(self.queryset,self.request.user)
    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def decide(self, request, pk=None):
        obj=self.get_object(); decision=request.data.get('status')
        if decision not in {'approved','rejected'}: return Response({'detail':'Ungültige Entscheidung.'},status=400)
        obj.status=decision; obj.decided_by=request.user; obj.save(); audit(request,'timeoff.decided',obj,{'status':decision}); return Response(self.get_serializer(obj).data)

class ShiftSwapViewSet(BaseModelViewSet):
    queryset=ShiftSwapRequest.objects.all(); serializer_class=ShiftSwapRequestSerializer
    def get_queryset(self):
        if self.request.user.role in {'admin','manager'}: return self.queryset
        return self.queryset.filter(Q(requested_by__user=self.request.user)|Q(offered_to__user=self.request.user))

class ContractTemplateViewSet(BaseModelViewSet):
    queryset=ContractTemplate.objects.all(); serializer_class=ContractTemplateSerializer; permission_classes=[IsAdminOrManager]

class ContractViewSet(BaseModelViewSet):
    queryset=Contract.objects.select_related('template','worker__user','client').all(); serializer_class=ContractSerializer; filterset_fields=['status','template__kind','worker','client']
    def get_queryset(self):
        user=self.request.user
        if user.role in {'admin','manager'}: return self.queryset
        if user.role=='worker': return self.queryset.filter(worker__user=user)
        return self.queryset.filter(client__contacts=user,client__contract_visibility_enabled=True)
    def perform_create(self, serializer):
        obj=serializer.save(created_by=self.request.user); audit(self.request,'contract.created',obj)
    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def generate_pdf(self, request, pk=None):
        contract=self.get_object(); contract.pdf.save(f'{contract.id}.pdf',render_contract_pdf(contract)); contract.status=Contract.Status.READY; contract.save(); audit(request,'contract.pdf_generated',contract); return Response(self.get_serializer(contract).data)
    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def send(self, request, pk=None):
        contract=self.get_object()
        if not contract.pdf: contract.pdf.save(f'{contract.id}.pdf',render_contract_pdf(contract))
        contract.status=Contract.Status.SENT; contract.sent_at=timezone.now(); contract.save(); audit(request,'contract.sent',contract); return Response(self.get_serializer(contract).data)
    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        contract=self.get_object()
        if contract.status not in {Contract.Status.READY,Contract.Status.SENT}: return Response({'detail':'Der Vertrag kann aktuell nicht unterzeichnet werden.'},status=400)
        sign_contract(contract,request.data.get('name','').strip(),request.data.get('signature',''),request)
        return Response(self.get_serializer(contract).data)

class DocumentViewSet(BaseModelViewSet):
    queryset=Document.objects.all(); serializer_class=DocumentSerializer; filterset_fields=['folder','worker','client']
    def get_queryset(self):
        u=self.request.user
        if u.role in {'admin','manager'}: return self.queryset
        if u.role=='worker': return self.queryset.filter(worker__user=u).exclude(visibility=Document.Visibility.ADMIN)
        return self.queryset.filter(client__contacts=u,visibility__in=[Document.Visibility.CLIENT,Document.Visibility.SHARED])
    def perform_create(self, serializer):
        values={'uploaded_by':self.request.user}
        if self.request.user.role=='worker': values['worker']=self.request.user.worker_profile
        if self.request.user.role=='client': values['client']=self.request.user.client_companies.first()
        obj=serializer.save(**values); audit(self.request,'document.uploaded',obj)

class PayrollViewSet(BaseModelViewSet):
    queryset=PayrollStatement.objects.all(); serializer_class=PayrollStatementSerializer
    def get_queryset(self): return scoped(self.queryset,self.request.user)

class RatingViewSet(BaseModelViewSet):
    queryset=WorkerRating.objects.all(); serializer_class=WorkerRatingSerializer
    def get_queryset(self):
        if self.request.user.role in {'admin','manager'}: return self.queryset
        if self.request.user.role=='worker': return self.queryset.filter(worker__user=self.request.user)
        return self.queryset.filter(client__contacts=self.request.user)
    def perform_create(self,serializer):
        obj=serializer.save(created_by=self.request.user); obj.worker.ranking_points += obj.score*10; obj.worker.save(update_fields=['ranking_points']); audit(self.request,'rating.created',obj)

class ConversationViewSet(BaseModelViewSet):
    queryset=Conversation.objects.prefetch_related('participants','messages').all(); serializer_class=ConversationSerializer
    def get_queryset(self): return self.queryset if self.request.user.role in {'admin','manager'} else self.queryset.filter(participants=self.request.user)
    @action(detail=True,methods=['post'])
    def post_message(self,request,pk=None):
        conv=self.get_object(); msg=Message.objects.create(conversation=conv,sender=request.user,body=request.data.get('body',''))
        return Response(MessageSerializer(msg,context={'request':request}).data,status=201)

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class=NotificationSerializer
    def get_queryset(self): return Notification.objects.filter(user=self.request.user).order_by('-created_at')
    @action(detail=True,methods=['post'])
    def read(self,request,pk=None):
        obj=self.get_object(); obj.read_at=timezone.now(); obj.save(); return Response(self.get_serializer(obj).data)

@api_view(['GET'])
def dashboard(request):
    user=request.user; now=timezone.now(); data={'role':user.role}
    if user.role in {'admin','manager'}:
        data.update({
            'workers': WorkerProfile.objects.filter(active=True).count(), 'clients': ClientCompany.objects.filter(active=True).count(),
            'open_shifts': Shift.objects.filter(is_open=True,starts_at__gte=now).count(),
            'pending_time_off': TimeOffRequest.objects.filter(status='pending').count(),
            'contracts_due': Contract.objects.filter(Q(ends_on__lte=now.date()+timedelta(days=30))|Q(reminder_date__lte=now.date()),status__in=['sent','signed','ready']).count(),
            'upcoming_shifts': ShiftSerializer(Shift.objects.filter(starts_at__gte=now).order_by('starts_at')[:8],many=True).data,
        })
    elif user.role=='worker':
        wp=user.worker_profile
        minutes=sum(x.worked_minutes for x in TimeEntry.objects.filter(worker=wp,clock_in__year=now.year,clock_in__month=now.month))
        data.update({'worked_minutes':minutes,'ranking_points':wp.ranking_points,'next_shifts':ShiftSerializer(Shift.objects.filter(worker=wp,starts_at__gte=now).order_by('starts_at')[:8],many=True).data,'open_shifts':Shift.objects.filter(is_open=True,status='published',starts_at__gte=now).count()})
    else:
        companies=user.client_companies.all(); data.update({'active_orders':ClientOrder.objects.filter(client__in=companies,status__in=['new','planning','confirmed']).count(),'upcoming_shifts':Shift.objects.filter(client__in=companies,starts_at__gte=now).count(),'contracts_to_sign':Contract.objects.filter(client__in=companies,status__in=['ready','sent']).count()})
    return Response(data)

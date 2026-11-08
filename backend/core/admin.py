from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import Q
from django.utils import timezone

from .models import *
from .shift_slots import ShiftSlot


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'role', 'is_active', 'wiw_id')
    fieldsets = UserAdmin.fieldsets + (('A+ Solution', {'fields': ('role', 'phone', 'avatar', 'locale', 'is_onboarded', 'deletion_requested_at', 'wiw_id', 'wiw_synced_at')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('A+ Solution', {'fields': ('email', 'role', 'first_name', 'last_name')}),)


class ShiftSlotAuditInline(admin.TabularInline):
    """Show assignment evidence without allowing edits to shift history."""

    model = ShiftSlot
    extra = 0
    can_delete = False
    fields = (
        'worker', 'status', 'source', 'claimed_at',
        'confirmation_status', 'confirmation_requested_at',
        'confirmation_decided_at', 'created_at',
    )
    readonly_fields = fields
    verbose_name = 'Schichtkarte und Übernahmedaten'
    verbose_name_plural = 'Schichtkarten und Übernahmedaten'

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = (
        'starts_at', 'ends_at', 'location', 'client',
        'assigned_staff', 'assignment_source', 'takeover_time',
        'status', 'note_preview',
    )
    list_filter = ('starts_at', 'status', 'client', 'location')
    search_fields = (
        'notes', 'location__name', 'client__name',
        'worker__user__first_name', 'worker__user__last_name',
        'slots__worker__user__first_name',
        'slots__worker__user__last_name',
    )
    list_select_related = ('client', 'location', 'worker__user')
    date_hierarchy = 'starts_at'
    ordering = ('-starts_at',)
    inlines = (ShiftSlotAuditInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('slots__worker__user')

    @staticmethod
    def _assigned_slots(obj):
        return [
            slot for slot in obj.slots.all()
            if slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id
        ]

    @admin.display(description='Mitarbeiter')
    def assigned_staff(self, obj):
        slots = self._assigned_slots(obj)
        names = [
            slot.worker.user.get_full_name() or slot.worker.user.email
            for slot in slots
        ]
        if not names and obj.worker_id:
            names = [obj.worker.user.get_full_name() or obj.worker.user.email]
        return ', '.join(dict.fromkeys(names)) or '—'

    @admin.display(description='Zuweisung durch')
    def assignment_source(self, obj):
        sources = [slot.source for slot in self._assigned_slots(obj)]
        return ', '.join(dict.fromkeys(sources)) or '—'

    @admin.display(description='Übernommen/zugewiesen am')
    def takeover_time(self, obj):
        times = [
            timezone.localtime(slot.claimed_at).strftime('%d.%m.%Y %H:%M')
            for slot in self._assigned_slots(obj) if slot.claimed_at
        ]
        return ', '.join(times) or '—'

    @admin.display(description='Notiz')
    def note_preview(self, obj):
        note = ' '.join((obj.notes or '').split())
        return note[:75] + ('…' if len(note) > 75 else '')



@admin.register(WorkerProfile)
class WorkerProfileAdmin(admin.ModelAdmin):
    """Searchable employee directory, including inactive historical profiles."""

    list_display = ('employee_name', 'employee_number', 'display_name', 'active', 'account_active', 'employment_type')
    search_fields = (
        'employee_number', 'display_name',
        'user__first_name', 'user__last_name', 'user__email',
        'wiw_user_id',
    )
    list_filter = ('active', 'user__is_active', 'employment_type')
    list_select_related = ('user',)
    ordering = ('user__last_name', 'user__first_name')
    list_per_page = 50

    @admin.display(description='Mitarbeiter', ordering='user__last_name')
    def employee_name(self, obj):
        return obj.user.get_full_name() or obj.display_name or obj.user.email

    @admin.display(boolean=True, description='Benutzer aktiv', ordering='user__is_active')
    def account_active(self, obj):
        return obj.user.is_active


class TimeEntrySourceFilter(admin.SimpleListFilter):
    title = 'Quelle'
    parameter_name = 'source'

    def lookups(self, request, model_admin):
        return (('wiw', 'WIW · Historie'), ('aplus', 'A+ · Zeiterfassung'))

    def queryset(self, request, queryset):
        if self.value() == 'wiw':
            return queryset.filter(wiw_time_id__isnull=False).exclude(wiw_time_id='')
        if self.value() == 'aplus':
            return queryset.filter(Q(wiw_time_id__isnull=True) | Q(wiw_time_id=''))
        return queryset


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    """Readable actual attendance records; planned shifts are only a reference."""

    list_display = (
        'employee_name', 'work_date', 'start_time', 'end_time',
        'pause_display', 'net_hours', 'work_location', 'source_display', 'approved',
    )
    search_fields = (
        'worker__user__first_name', 'worker__user__last_name',
        'worker__user__email', 'worker__employee_number',
        'worker__display_name', 'worker__wiw_user_id',
        '=wiw_time_id',
    )
    list_filter = (
        TimeEntrySourceFilter, 'approved', 'worker__active',
        ('worker', admin.RelatedOnlyFieldListFilter),
        ('shift__client', admin.RelatedOnlyFieldListFilter),
        'clock_in',
    )
    list_select_related = ('worker__user', 'shift__client', 'shift__location')
    autocomplete_fields = ('worker', 'shift', 'approved_by')
    date_hierarchy = 'clock_in'
    ordering = ('-clock_in',)
    list_per_page = 50
    show_full_result_count = False

    @admin.display(description='Mitarbeiter', ordering='worker__user__last_name')
    def employee_name(self, obj):
        worker = obj.worker
        name = worker.user.get_full_name() or worker.display_name or worker.user.email
        return f'{name} · {worker.employee_number}'

    @admin.display(description='Datum', ordering='clock_in')
    def work_date(self, obj):
        return timezone.localtime(obj.clock_in).strftime('%d.%m.%Y')

    @admin.display(description='Beginn', ordering='clock_in')
    def start_time(self, obj):
        return timezone.localtime(obj.clock_in).strftime('%H:%M')

    @admin.display(description='Ende', ordering='clock_out')
    def end_time(self, obj):
        return timezone.localtime(obj.clock_out).strftime('%H:%M') if obj.clock_out else 'Offen'

    @admin.display(description='Pause')
    def pause_display(self, obj):
        return f'{obj.effective_break_minutes} Min.'

    @admin.display(description='Netto')
    def net_hours(self, obj):
        if not obj.clock_out:
            return '—'
        return f'{obj.worked_minutes / 60:.2f}'.replace('.', ',') + ' Std.'

    @admin.display(description='Kunde / Einsatzort')
    def work_location(self, obj):
        if not obj.shift_id:
            return '—'
        client = obj.shift.client.name if obj.shift.client_id else ''
        location = obj.shift.location.name if obj.shift.location_id else ''
        return ' · '.join(item for item in (client, location) if item) or '—'

    @admin.display(description='Quelle')
    def source_display(self, obj):
        return 'WIW · Historie' if obj.wiw_time_id else 'A+'

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'actor', 'object_type', 'object_id')
    list_filter = ('created_at', 'action', 'object_type')
    search_fields = (
        '=object_id', 'action', 'actor__first_name',
        'actor__last_name', 'actor__email',
    )
    list_select_related = ('actor',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)


for model in [
    ClientCompany, EmployeeMasterData, Location, Position, ClientOrder,
    Availability, TimeOffRequest, ShiftSwapRequest, ContractTemplate,
    Contract, ContractSignature, Document, PayrollStatement, WorkerRating, Conversation,
    Message, Notification, IntegrationSyncRun, WebhookEvent, ShiftImportPackage,
    ShiftImportRevision, WorkingTimeSetting, WorkingTimeAccountRecord, WorkingTimeSyncLog,
]:
    admin.site.register(model)

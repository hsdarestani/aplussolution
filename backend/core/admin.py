from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
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
    ClientCompany, WorkerProfile, EmployeeMasterData, Location, Position, ClientOrder,
    Availability, TimeEntry, TimeOffRequest, ShiftSwapRequest, ContractTemplate,
    Contract, ContractSignature, Document, PayrollStatement, WorkerRating, Conversation,
    Message, Notification, IntegrationSyncRun, WebhookEvent, ShiftImportPackage,
    ShiftImportRevision, WorkingTimeSetting, WorkingTimeAccountRecord, WorkingTimeSyncLog,
]:
    admin.site.register(model)

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import *


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'role', 'is_active', 'wiw_id')
    fieldsets = UserAdmin.fieldsets + (('A+ Solution', {'fields': ('role', 'phone', 'avatar', 'locale', 'is_onboarded', 'deletion_requested_at', 'wiw_id', 'wiw_synced_at')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('A+ Solution', {'fields': ('email', 'role', 'first_name', 'last_name')}),)


for model in [
    ClientCompany, WorkerProfile, EmployeeMasterData, Location, Position, ClientOrder,
    Availability, Shift, TimeEntry, TimeOffRequest, ShiftSwapRequest, ContractTemplate,
    Contract, ContractSignature, Document, PayrollStatement, WorkerRating, Conversation,
    Message, Notification, AuditLog, IntegrationSyncRun, WebhookEvent, ShiftImportPackage,
    ShiftImportRevision, WorkingTimeSetting, WorkingTimeAccountRecord, WorkingTimeSyncLog,
]:
    admin.site.register(model)

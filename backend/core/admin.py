from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model=User; ordering=('email',); list_display=('email','first_name','last_name','role','is_active')
    fieldsets=UserAdmin.fieldsets+(('A+ Solution',{'fields':('role','phone','avatar','locale','is_onboarded','deletion_requested_at')}),)
    add_fieldsets=UserAdmin.add_fieldsets+(('A+ Solution',{'fields':('email','role','first_name','last_name')}),)
for model in [ClientCompany,WorkerProfile,Location,Position,ClientOrder,Availability,Shift,TimeEntry,TimeOffRequest,ShiftSwapRequest,ContractTemplate,Contract,Document,PayrollStatement,WorkerRating,Conversation,Message,Notification,AuditLog]: admin.site.register(model)

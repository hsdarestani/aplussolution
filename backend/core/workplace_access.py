from .models import Location, User, WorkerProfile
from .scheduling_models import ScheduleGroup
from .workplace_models import AccessRole, UserAccessAssignment, WorkplaceSettings


CAPABILITIES = {
    'manager.access',
    'workplace.view', 'workplace.manage',
    'roles.view', 'roles.manage',
    'people.view', 'people.edit',
    'clients.view', 'clients.edit',
    'schedule.view', 'schedule.edit', 'schedule.publish',
    'attendance.view', 'attendance.edit',
    'payroll.view', 'payroll.review', 'payroll.export',
    'wage.view', 'labor.share',
    'reports.view', 'documents.manage',
}

MANAGER_LEGACY_CAPABILITIES = CAPABILITIES - {'roles.manage', 'workplace.manage'}

SYSTEM_ROLES = {
    'dispatcher': {
        'name': 'Disponent',
        'description': 'Dienstplanung, Personal, Attendance und Abrechnung im gesamten Betrieb.',
        'permissions': sorted(MANAGER_LEGACY_CAPABILITIES),
        'wage_visibility': AccessRole.WageVisibility.ALL,
    },
    'supervisor': {
        'name': 'Supervisor',
        'description': 'Operative Führung nur für zugeordnete Teams, Dienstpläne und Standorte.',
        'permissions': [
            'manager.access', 'workplace.view', 'people.view', 'schedule.view', 'schedule.edit',
            'schedule.publish', 'attendance.view', 'attendance.edit', 'payroll.view', 'payroll.review',
            'wage.view', 'labor.share', 'reports.view',
        ],
        'wage_visibility': AccessRole.WageVisibility.SCOPED,
    },
    'scheduler': {
        'name': 'Dienstplaner',
        'description': 'Plant und veröffentlicht Schichten ohne Zugriff auf Löhne oder Payroll.',
        'permissions': ['manager.access', 'people.view', 'schedule.view', 'schedule.edit', 'schedule.publish', 'labor.share'],
        'wage_visibility': AccessRole.WageVisibility.NONE,
    },
    'payroll': {
        'name': 'Lohn & Zeiten',
        'description': 'Prüft Arbeitszeiten und Pay Periods, ohne Dienstpläne zu bearbeiten.',
        'permissions': ['manager.access', 'people.view', 'attendance.view', 'attendance.edit', 'payroll.view', 'payroll.review', 'payroll.export', 'wage.view', 'reports.view'],
        'wage_visibility': AccessRole.WageVisibility.ALL,
    },
    'viewer': {
        'name': 'Nur Lesen',
        'description': 'Lesender Zugriff auf operative Daten im zugeordneten Bereich.',
        'permissions': ['manager.access', 'workplace.view', 'people.view', 'schedule.view', 'attendance.view', 'reports.view'],
        'wage_visibility': AccessRole.WageVisibility.NONE,
    },
}


def seed_system_roles():
    roles = []
    for code, values in SYSTEM_ROLES.items():
        role, _ = AccessRole.objects.update_or_create(
            code=code,
            defaults={**values, 'is_system': True, 'active': True},
        )
        roles.append(role)
    WorkplaceSettings.load()
    return roles


def assignment_for(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    try:
        assignment = user.access_assignment
    except UserAccessAssignment.DoesNotExist:
        return None
    if not assignment.active or not assignment.access_role.active:
        return None
    return assignment


def capabilities_for_user(user):
    if not getattr(user, 'is_authenticated', False):
        return []
    if user.role == User.Role.ADMIN or user.is_superuser:
        return sorted(CAPABILITIES)
    if user.role == User.Role.MANAGER:
        assignment = assignment_for(user)
        if not assignment:
            return sorted(MANAGER_LEGACY_CAPABILITIES)
        return sorted(set(assignment.access_role.permissions or []) & CAPABILITIES)
    if user.role == User.Role.WORKER:
        return ['attendance.view', 'schedule.view']
    return []


def has_capability(user, capability, *, worker=None, location=None):
    if capability not in CAPABILITIES or capability not in capabilities_for_user(user):
        return False
    if user.role == User.Role.ADMIN or user.is_superuser:
        return True
    assignment = assignment_for(user)
    if user.role == User.Role.MANAGER and assignment and assignment.scope_mode == UserAccessAssignment.ScopeMode.SCOPED:
        if worker is not None and not worker_in_scope(user, worker):
            return False
        if location is not None and not location_in_scope(user, location):
            return False
    return True


def visible_schedule_groups(user, queryset=None):
    qs = queryset if queryset is not None else ScheduleGroup.objects.all()
    if user.role == User.Role.ADMIN or user.is_superuser:
        return qs
    assignment = assignment_for(user)
    if user.role != User.Role.MANAGER:
        return qs.none()
    if not assignment or assignment.scope_mode == UserAccessAssignment.ScopeMode.ALL:
        return qs
    explicit_ids = list(assignment.schedule_groups.values_list('id', flat=True))
    location_ids = list(assignment.locations.values_list('id', flat=True))
    return qs.filter(id__in=explicit_ids).union(qs.filter(locations__id__in=location_ids)).distinct() if location_ids else qs.filter(id__in=explicit_ids)


def visible_locations(user, queryset=None):
    qs = queryset if queryset is not None else Location.objects.all()
    if user.role == User.Role.ADMIN or user.is_superuser:
        return qs
    assignment = assignment_for(user)
    if user.role != User.Role.MANAGER:
        return qs.none()
    if not assignment or assignment.scope_mode == UserAccessAssignment.ScopeMode.ALL:
        return qs
    location_ids = set(assignment.locations.values_list('id', flat=True))
    location_ids.update(
        Location.objects.filter(schedule_groups__in=assignment.schedule_groups.all()).values_list('id', flat=True)
    )
    return qs.filter(id__in=location_ids).distinct()


def worker_in_scope(user, worker):
    if user.role == User.Role.ADMIN or user.is_superuser:
        return True
    if user.role == User.Role.WORKER:
        return getattr(worker, 'user_id', None) == user.id
    assignment = assignment_for(user)
    if user.role != User.Role.MANAGER:
        return False
    if not assignment or assignment.scope_mode == UserAccessAssignment.ScopeMode.ALL:
        return True
    if assignment.workers.filter(pk=worker.pk).exists():
        return True
    schedule_ids = assignment.schedule_groups.values_list('id', flat=True)
    if worker.schedule_memberships.filter(active=True, schedule_id__in=schedule_ids).exists():
        return True
    location_ids = visible_locations(user).values_list('id', flat=True)
    if worker.shifts.filter(location_id__in=location_ids).exists():
        return True
    from .shift_slots import ShiftSlot
    return ShiftSlot.objects.filter(worker=worker, shift__location_id__in=location_ids).exists()


def location_in_scope(user, location):
    if user.role == User.Role.ADMIN or user.is_superuser:
        return True
    if user.role != User.Role.MANAGER:
        return False
    assignment = assignment_for(user)
    if not assignment or assignment.scope_mode == UserAccessAssignment.ScopeMode.ALL:
        return True
    return visible_locations(user).filter(pk=location.pk).exists()


def visible_workers(user, queryset=None):
    qs = queryset if queryset is not None else WorkerProfile.objects.all()
    if user.role == User.Role.ADMIN or user.is_superuser:
        return qs
    if user.role == User.Role.WORKER:
        return qs.filter(user=user)
    assignment = assignment_for(user)
    if user.role != User.Role.MANAGER:
        return qs.none()
    if not assignment or assignment.scope_mode == UserAccessAssignment.ScopeMode.ALL:
        return qs
    worker_ids = set(assignment.workers.values_list('id', flat=True))
    worker_ids.update(
        WorkerProfile.objects.filter(
            schedule_memberships__active=True,
            schedule_memberships__schedule__in=assignment.schedule_groups.all(),
        ).values_list('id', flat=True)
    )
    location_ids = list(visible_locations(user).values_list('id', flat=True))
    if location_ids:
        worker_ids.update(qs.filter(shifts__location_id__in=location_ids).values_list('id', flat=True))
        from .shift_slots import ShiftSlot
        worker_ids.update(ShiftSlot.objects.filter(shift__location_id__in=location_ids, worker__isnull=False).values_list('worker_id', flat=True))
    return qs.filter(id__in=worker_ids).distinct()


def can_view_wage(user, worker=None):
    if user.role == User.Role.ADMIN or user.is_superuser:
        return True
    if user.role == User.Role.WORKER:
        return worker is not None and worker.user_id == user.id
    if user.role != User.Role.MANAGER or not has_capability(user, 'wage.view'):
        return False
    assignment = assignment_for(user)
    if not assignment:
        return True
    visibility = assignment.access_role.wage_visibility
    if visibility == AccessRole.WageVisibility.ALL:
        return True
    if visibility == AccessRole.WageVisibility.SCOPED:
        return worker is None or worker_in_scope(user, worker)
    return False


def can_share_labor(user):
    settings = WorkplaceSettings.load()
    if not settings.labor_sharing_enabled or not has_capability(user, 'labor.share'):
        return False
    if user.role == User.Role.ADMIN or user.is_superuser:
        return True
    assignment = assignment_for(user)
    return bool(not assignment or assignment.can_share_labor)


def scope_snapshot(user):
    assignment = assignment_for(user)
    if not assignment:
        return {'mode': 'all' if user.role in {User.Role.ADMIN, User.Role.MANAGER} else 'self', 'schedules': [], 'locations': [], 'workers': []}
    return {
        'mode': assignment.scope_mode,
        'schedules': list(assignment.schedule_groups.values_list('id', flat=True)),
        'locations': list(assignment.locations.values_list('id', flat=True)),
        'workers': list(assignment.workers.values_list('id', flat=True)),
        'can_share_labor': assignment.can_share_labor,
        'role': assignment.access_role.code,
        'wage_visibility': assignment.access_role.wage_visibility,
    }

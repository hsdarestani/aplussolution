"""Keep derived monthly payroll accounts in sync with authoritative attendance.

TimeEntry is the source of actual hours. A+ monthly ledgers are materialized
derivatives; updating attendance must not require a separate manual rebuild.
Never auto-modify imported legacy ledgers or imported Lexware payroll evidence.
"""
import logging
from contextlib import contextmanager
from contextvars import ContextVar

from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Shift, TimeEntry, WorkerProfile

logger = logging.getLogger(__name__)
_batched_changes = ContextVar('attendance_account_batched_changes', default=None)


def _snapshot(entry):
    if not entry.clock_in:
        return None
    local_day = timezone.localtime(entry.clock_in).date()
    return (
        str(entry.worker_id),
        local_day.replace(day=1),
        entry.clock_in,
        entry.clock_out,
        bool(entry.approved),
        entry.break_minutes,
        str(entry.shift_id or ''),
        str(entry.wiw_time_id or ''),
    )


def _affected(previous, current):
    if previous == current:
        return set()
    return {
        (snapshot[0], snapshot[1])
        for snapshot in (previous, current)
        if snapshot and snapshot[3] is not None
    }


def _run_changes(changes):
    # A single worker-level rebuild recalculates the modified month and
    # propagates its running balance to subsequent A+ account records.
    earliest = {}
    for worker_id, month in changes:
        if worker_id not in earliest or month < earliest[worker_id]:
            earliest[worker_id] = month
    for worker_id, month in sorted(earliest.items()):
        try:
            reconcile_worker_month(worker_id, month)
        except Exception:
            # The TimeEntry mutation is already committed; never disguise it
            # as a failed save. A repeated reconciliation or manual repair is
            # idempotent, and production error logs retain the failure.
            logger.exception(
                'Attendance account reconciliation failed for worker %s from %s',
                worker_id, month,
            )


def _queue(changes):
    if not changes:
        return
    bucket = _batched_changes.get()
    if bucket is not None:
        bucket.update(changes)
        return
    transaction.on_commit(lambda changed=frozenset(changes): _run_changes(changed))


@contextmanager
def batch_attendance_changes():
    """Coalesce many WIW time-row upserts into one refresh per affected worker."""
    active = _batched_changes.get()
    if active is not None:
        yield
        return
    changed = set()
    token = _batched_changes.set(changed)
    try:
        yield
        if changed:
            transaction.on_commit(
                lambda items=frozenset(changed): _run_changes(items)
            )
    finally:
        _batched_changes.reset(token)


def reconcile_worker_month(worker_id, month):
    """Refresh only the worker's A+ ledger, preserving all Lexware source data.

    Lock the worker before reading attendance and writing the monthly records
    so concurrent approvals cannot overwrite each other's derived totals.
    """
    from .payroll_engine import sync_working_time

    with transaction.atomic():
        worker = (
            WorkerProfile.objects.select_for_update()
            .filter(pk=worker_id).first()
        )
        if worker is None:
            return
        today = timezone.localdate()
        end = max(today, month)
        sync_working_time(
            month,
            end,
            include_inactive_workers=True,
            worker_ids=[worker.pk],
            attendance_change=True,
        )


@receiver(pre_save, sender=TimeEntry, dispatch_uid='attendance_account_pre_save')
def capture_previous_entry(sender, instance, **kwargs):
    previous = None
    if instance.pk:
        prior = TimeEntry.objects.filter(pk=instance.pk).only(
            'worker_id', 'clock_in', 'clock_out', 'approved',
            'break_minutes', 'shift_id', 'wiw_time_id'
        ).first()
        if prior is not None:
            previous = _snapshot(prior)
    instance._attendance_previous = previous


@receiver(post_save, sender=TimeEntry, dispatch_uid='attendance_account_post_save')
def attendance_entry_saved(sender, instance, **kwargs):
    _queue(_affected(getattr(instance, '_attendance_previous', None), _snapshot(instance)))


@receiver(post_delete, sender=TimeEntry, dispatch_uid='attendance_account_post_delete')
def attendance_entry_deleted(sender, instance, **kwargs):
    _queue(_affected(_snapshot(instance), None))


def _shift_snapshot(shift):
    return (
        shift.starts_at, shift.ends_at, shift.break_minutes,
        shift.client_id, shift.location_id, shift.position_id,
    )


def _affected_shift_attendance(shift_id):
    return {
        (_snapshot(entry)[0], _snapshot(entry)[1])
        for entry in TimeEntry.objects.filter(
            shift_id=shift_id, clock_out__isnull=False
        ).filter(Q(approved=True) | Q(wiw_time_id__isnull=False))
        .only('worker_id', 'clock_in', 'clock_out', 'approved', 'wiw_time_id')
        if _snapshot(entry) is not None
    }


@receiver(pre_save, sender=Shift, dispatch_uid='attendance_account_shift_pre_save')
def capture_previous_shift(sender, instance, **kwargs):
    prior = Shift.objects.filter(pk=instance.pk).only(
        'starts_at', 'ends_at', 'break_minutes',
        'client_id', 'location_id', 'position_id',
    ).first() if instance.pk else None
    instance._attendance_previous_shift = _shift_snapshot(prior) if prior else None


@receiver(post_save, sender=Shift, dispatch_uid='attendance_account_shift_post_save')
def attendance_shift_saved(sender, instance, **kwargs):
    prior = getattr(instance, '_attendance_previous_shift', None)
    if prior is not None and prior != _shift_snapshot(instance):
        _queue(_affected_shift_attendance(instance.pk))


@receiver(pre_delete, sender=Shift, dispatch_uid='attendance_account_shift_pre_delete')
def capture_deleted_shift_hours(sender, instance, **kwargs):
    instance._attendance_affected_shift = _affected_shift_attendance(instance.pk)


@receiver(post_delete, sender=Shift, dispatch_uid='attendance_account_shift_post_delete')
def attendance_shift_deleted(sender, instance, **kwargs):
    _queue(getattr(instance, '_attendance_affected_shift', set()))

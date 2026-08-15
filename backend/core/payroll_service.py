from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .attendance_v4_models import AttendanceNotice
from .models import TimeEntry, WorkerProfile
from .payroll_models import PayPeriod, TimesheetEntry, TimesheetException, WorkerTimesheet
from .shift_slots import ShiftSlot


MONEY = Decimal('0.01')


def assert_period_editable(period):
    if period.status in {PayPeriod.Status.CLOSED, PayPeriod.Status.LOCKED}:
        raise ValidationError('Dieser Abrechnungszeitraum ist geschlossen oder gesperrt.')


def assert_time_entry_editable(entry):
    try:
        snapshot = entry.timesheet_snapshot
    except TimesheetEntry.DoesNotExist:
        return
    if snapshot.timesheet.pay_period.status in {PayPeriod.Status.CLOSED, PayPeriod.Status.LOCKED}:
        raise ValidationError('Dieser Zeiteintrag gehört zu einem geschlossenen Abrechnungszeitraum.')


def _entry_break_totals(entry):
    breaks = list(entry.attendance_breaks.exclude(status='cancelled'))
    paid = 0
    unpaid = 0
    for item in breaks:
        if item.paid:
            if item.status == 'completed':
                paid += item.actual_minutes
        else:
            unpaid += item.deductible_minutes
    if not breaks and entry.shift_id and not entry.clock_events.exists():
        # Historical entries created before Attendance V4 keep their legacy scheduled deduction.
        unpaid = int(entry.shift.break_minutes or 0)
    return paid, unpaid


def entry_financials(entry):
    end = entry.clock_out or timezone.now()
    gross = max(0, int((end - entry.clock_in).total_seconds() // 60))
    paid_breaks, unpaid_breaks = _entry_break_totals(entry)
    net = max(0, gross - unpaid_breaks)
    rate = Decimal(entry.worker.tariff_hourly_rate or 0) + Decimal(entry.worker.extra_allowance or 0)
    amount = ((Decimal(net) / Decimal(60)) * rate).quantize(MONEY, rounding=ROUND_HALF_UP)
    return {
        'gross_minutes': gross,
        'paid_break_minutes': paid_breaks,
        'unpaid_break_minutes': unpaid_breaks,
        'net_minutes': net,
        'hourly_rate': rate.quantize(MONEY, rounding=ROUND_HALF_UP),
        'amount_estimate': amount,
    }


def _exception(sheet, key, exception_type, severity, *, shift=None, time_entry=None, attendance_notice=None, details=None):
    obj, _ = TimesheetException.objects.update_or_create(
        dedupe_key=key,
        defaults={
            'timesheet': sheet,
            'exception_type': exception_type,
            'severity': severity,
            'status': TimesheetException.Status.OPEN,
            'shift': shift,
            'time_entry': time_entry,
            'attendance_notice': attendance_notice,
            'details': details or {},
            'resolved_by': None,
            'resolved_at': None,
            'resolution_note': '',
        },
    )
    return obj


def _refresh_sheet_totals(sheet):
    entries = list(sheet.entries.all())
    open_exceptions = sheet.exceptions.filter(status=TimesheetException.Status.OPEN)
    sheet.gross_minutes = sum(item.gross_minutes for item in entries)
    sheet.paid_break_minutes = sum(item.paid_break_minutes for item in entries)
    sheet.unpaid_break_minutes = sum(item.unpaid_break_minutes for item in entries)
    sheet.net_minutes = sum(item.net_minutes for item in entries)
    sheet.gross_estimate = sum((item.amount_estimate for item in entries), Decimal('0.00'))
    sheet.entry_count = len(entries)
    sheet.exception_count = open_exceptions.count()
    sheet.blocking_exception_count = open_exceptions.filter(severity=TimesheetException.Severity.BLOCKING).count()
    sheet.save(update_fields=[
        'gross_minutes', 'paid_break_minutes', 'unpaid_break_minutes', 'net_minutes', 'gross_estimate',
        'entry_count', 'exception_count', 'blocking_exception_count', 'updated_at',
    ])
    return sheet


@transaction.atomic
def sync_period(period):
    assert_period_editable(period)
    entries = list(
        TimeEntry.objects.filter(clock_in__date__gte=period.starts_on, clock_in__date__lte=period.ends_on)
        .select_related('worker__user', 'shift')
        .prefetch_related('attendance_breaks', 'clock_events')
        .order_by('clock_in')
    )
    now = timezone.now()
    claimed_slots = list(
        ShiftSlot.objects.filter(
            status=ShiftSlot.Status.CLAIMED,
            worker__isnull=False,
            shift__starts_at__date__gte=period.starts_on,
            shift__starts_at__date__lte=period.ends_on,
            shift__ends_at__lte=now,
        ).select_related('worker__user', 'shift')
    )
    worker_ids = {item.worker_id for item in entries} | {item.worker_id for item in claimed_slots}
    workers = WorkerProfile.objects.filter(id__in=worker_ids).select_related('user').order_by('employee_number')
    result = []

    for worker in workers:
        sheet, created = WorkerTimesheet.objects.get_or_create(pay_period=period, worker=worker)
        if not created and sheet.status == WorkerTimesheet.Status.APPROVED:
            sheet.status = WorkerTimesheet.Status.REOPENED
            sheet.approved_at = None
            sheet.approved_by = None
            sheet.revision += 1
            sheet.save(update_fields=['status', 'approved_at', 'approved_by', 'revision', 'updated_at'])

        active_keys = set()
        worker_entries = [item for item in entries if item.worker_id == worker.id]
        for entry in worker_entries:
            financials = entry_financials(entry)
            snapshot = TimesheetEntry.objects.filter(time_entry=entry).first()
            defaults = {
                'timesheet': sheet,
                'clock_in': entry.clock_in,
                'clock_out': entry.clock_out,
                **financials,
                'review_status': TimesheetEntry.ReviewStatus.APPROVED if entry.approved else TimesheetEntry.ReviewStatus.PENDING,
                'reviewed_by': entry.approved_by if entry.approved else None,
                'reviewed_at': timezone.now() if entry.approved and snapshot is None else (snapshot.reviewed_at if snapshot else None),
                'locked': False,
            }
            TimesheetEntry.objects.update_or_create(time_entry=entry, defaults=defaults)
            if entry.clock_out is None:
                key = f'{sheet.id}:running:{entry.id}'
                active_keys.add(key)
                _exception(sheet, key, TimesheetException.Type.RUNNING_ENTRY, TimesheetException.Severity.BLOCKING, time_entry=entry)
            if not entry.approved:
                key = f'{sheet.id}:unapproved:{entry.id}'
                active_keys.add(key)
                _exception(sheet, key, TimesheetException.Type.UNAPPROVED_ENTRY, TimesheetException.Severity.WARNING, time_entry=entry)

        for slot in [item for item in claimed_slots if item.worker_id == worker.id]:
            if not TimeEntry.objects.filter(worker=worker, shift=slot.shift).exists():
                key = f'{sheet.id}:missing:{slot.shift_id}:{slot.id}'
                active_keys.add(key)
                _exception(
                    sheet,
                    key,
                    TimesheetException.Type.MISSING_ENTRY,
                    TimesheetException.Severity.BLOCKING,
                    shift=slot.shift,
                    details={'slot': str(slot.id), 'scheduled_start': slot.shift.starts_at.isoformat(), 'scheduled_end': slot.shift.ends_at.isoformat()},
                )

        notices = AttendanceNotice.objects.filter(
            worker=worker,
            status__in=[AttendanceNotice.Status.OPEN, AttendanceNotice.Status.ACKNOWLEDGED],
        ).filter(
            Q(entry__clock_in__date__gte=period.starts_on, entry__clock_in__date__lte=period.ends_on)
            | Q(shift__starts_at__date__gte=period.starts_on, shift__starts_at__date__lte=period.ends_on)
        )
        for notice in notices:
            key = f'{sheet.id}:notice:{notice.id}'
            active_keys.add(key)
            severity = TimesheetException.Severity.BLOCKING if notice.severity == AttendanceNotice.Severity.CRITICAL else TimesheetException.Severity.WARNING
            _exception(
                sheet,
                key,
                TimesheetException.Type.ATTENDANCE_NOTICE,
                severity,
                shift=notice.shift,
                time_entry=notice.entry,
                attendance_notice=notice,
                details={'notice_type': notice.notice_type, 'severity': notice.severity},
            )

        stale = sheet.exceptions.filter(status=TimesheetException.Status.OPEN)
        if active_keys:
            stale = stale.exclude(dedupe_key__in=active_keys)
        stale.update(status=TimesheetException.Status.RESOLVED, resolved_at=timezone.now(), resolution_note='Automatisch beim Sync aufgelöst.')
        _refresh_sheet_totals(sheet)
        result.append(sheet)

    period.status = PayPeriod.Status.REVIEW if result else PayPeriod.Status.OPEN
    period.save(update_fields=['status', 'updated_at'])
    return result


@transaction.atomic
def review_entry(snapshot, user, decision, note=''):
    assert_period_editable(snapshot.timesheet.pay_period)
    if decision not in {TimesheetEntry.ReviewStatus.APPROVED, TimesheetEntry.ReviewStatus.REJECTED}:
        raise ValidationError('Ungültige Prüfentscheidung.')
    snapshot.review_status = decision
    snapshot.reviewed_by = user
    snapshot.reviewed_at = timezone.now()
    snapshot.review_note = note
    snapshot.time_entry.approved = decision == TimesheetEntry.ReviewStatus.APPROVED
    snapshot.time_entry.approved_by = user if snapshot.time_entry.approved else None
    snapshot.time_entry.save(update_fields=['approved', 'approved_by', 'updated_at'])
    snapshot.save(update_fields=['review_status', 'reviewed_by', 'reviewed_at', 'review_note', 'updated_at'])

    snapshot.timesheet.exceptions.filter(
        time_entry=snapshot.time_entry,
        exception_type__in=[TimesheetException.Type.UNAPPROVED_ENTRY, TimesheetException.Type.REJECTED_ENTRY],
        status=TimesheetException.Status.OPEN,
    ).update(status=TimesheetException.Status.RESOLVED, resolved_by=user, resolved_at=timezone.now(), resolution_note='Durch Entry-Prüfung aufgelöst.')
    if decision == TimesheetEntry.ReviewStatus.REJECTED:
        _exception(
            snapshot.timesheet,
            f'{snapshot.timesheet_id}:rejected:{snapshot.time_entry_id}',
            TimesheetException.Type.REJECTED_ENTRY,
            TimesheetException.Severity.BLOCKING,
            time_entry=snapshot.time_entry,
            details={'note': note},
        )
    _refresh_sheet_totals(snapshot.timesheet)
    return snapshot


@transaction.atomic
def approve_all_entries(sheet, user):
    assert_period_editable(sheet.pay_period)
    for snapshot in sheet.entries.select_related('time_entry'):
        if snapshot.review_status != TimesheetEntry.ReviewStatus.APPROVED:
            review_entry(snapshot, user, TimesheetEntry.ReviewStatus.APPROVED, 'Sammelfreigabe')
    _refresh_sheet_totals(sheet)
    return sheet


@transaction.atomic
def submit_timesheet(sheet):
    assert_period_editable(sheet.pay_period)
    sheet.status = WorkerTimesheet.Status.SUBMITTED
    sheet.submitted_at = timezone.now()
    sheet.save(update_fields=['status', 'submitted_at', 'updated_at'])
    return sheet


@transaction.atomic
def approve_timesheet(sheet, user, note=''):
    assert_period_editable(sheet.pay_period)
    _refresh_sheet_totals(sheet)
    if sheet.blocking_exception_count:
        raise ValidationError('Blockierende Timesheet-Ausnahmen müssen zuerst gelöst werden.')
    if sheet.entries.exclude(review_status=TimesheetEntry.ReviewStatus.APPROVED).exists():
        raise ValidationError('Alle Zeiteinträge müssen vor der Timesheet-Freigabe geprüft sein.')
    sheet.status = WorkerTimesheet.Status.APPROVED
    sheet.approved_by = user
    sheet.approved_at = timezone.now()
    sheet.review_note = note
    sheet.save(update_fields=['status', 'approved_by', 'approved_at', 'review_note', 'updated_at'])
    return sheet


@transaction.atomic
def unapprove_timesheet(sheet, user, note=''):
    assert_period_editable(sheet.pay_period)
    sheet.status = WorkerTimesheet.Status.REOPENED
    sheet.approved_by = None
    sheet.approved_at = None
    sheet.review_note = note
    sheet.revision += 1
    sheet.save(update_fields=['status', 'approved_by', 'approved_at', 'review_note', 'revision', 'updated_at'])
    return sheet


@transaction.atomic
def close_period(period, user):
    if period.status == PayPeriod.Status.LOCKED:
        raise ValidationError('Gesperrte Abrechnungszeiträume können nicht geschlossen werden.')
    sheets = period.timesheets.all()
    if not sheets.exists():
        raise ValidationError('Der Abrechnungszeitraum enthält noch keine Timesheets. Bitte zuerst synchronisieren.')
    if sheets.exclude(status=WorkerTimesheet.Status.APPROVED).exists():
        raise ValidationError('Alle Timesheets müssen vor dem Schließen freigegeben sein.')
    if TimesheetException.objects.filter(timesheet__pay_period=period, status=TimesheetException.Status.OPEN, severity=TimesheetException.Severity.BLOCKING).exists():
        raise ValidationError('Es bestehen noch blockierende Ausnahmen.')
    period.status = PayPeriod.Status.CLOSED
    period.closed_by = user
    period.closed_at = timezone.now()
    period.save(update_fields=['status', 'closed_by', 'closed_at', 'updated_at'])
    WorkerTimesheet.objects.filter(pay_period=period).update(status=WorkerTimesheet.Status.LOCKED, locked_at=timezone.now())
    TimesheetEntry.objects.filter(timesheet__pay_period=period).update(locked=True)
    return period


@transaction.atomic
def reopen_period(period, user, note=''):
    if period.status != PayPeriod.Status.CLOSED:
        raise ValidationError('Nur geschlossene Abrechnungszeiträume können wieder geöffnet werden.')
    period.status = PayPeriod.Status.OPEN
    period.closed_by = None
    period.closed_at = None
    period.reopen_count += 1
    if note:
        period.notes = f'{period.notes}\nReopen: {note}'.strip()
    period.save(update_fields=['status', 'closed_by', 'closed_at', 'reopen_count', 'notes', 'updated_at'])
    WorkerTimesheet.objects.filter(pay_period=period).update(status=WorkerTimesheet.Status.REOPENED, locked_at=None, approved_by=None, approved_at=None)
    TimesheetEntry.objects.filter(timesheet__pay_period=period).update(locked=False)
    return period


@transaction.atomic
def lock_period(period, user):
    if period.status != PayPeriod.Status.CLOSED:
        raise ValidationError('Nur ein geschlossener Abrechnungszeitraum kann endgültig gesperrt werden.')
    period.status = PayPeriod.Status.LOCKED
    period.locked_by = user
    period.locked_at = timezone.now()
    period.save(update_fields=['status', 'locked_by', 'locked_at', 'updated_at'])
    return period


@transaction.atomic
def unlock_period(period, user, note=''):
    if period.status != PayPeriod.Status.LOCKED:
        raise ValidationError('Der Abrechnungszeitraum ist nicht gesperrt.')
    period.status = PayPeriod.Status.CLOSED
    period.locked_by = None
    period.locked_at = None
    if note:
        period.notes = f'{period.notes}\nUnlock: {note}'.strip()
    period.save(update_fields=['status', 'locked_by', 'locked_at', 'notes', 'updated_at'])
    return period

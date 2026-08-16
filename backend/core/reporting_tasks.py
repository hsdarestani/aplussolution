from celery import shared_task
from django.utils import timezone

from .reporting_models import ReportRun, ReportSchedule
from .reporting_service import _next_run, send_scheduled_report


@shared_task
def deliver_due_reports():
    now = timezone.now()
    due = list(ReportSchedule.objects.filter(active=True, next_run_at__lte=now).select_related('report', 'created_by')[:100])
    delivered = 0
    failed = 0
    for schedule in due:
        try:
            send_scheduled_report(schedule)
            delivered += 1
        except Exception as exc:
            failed += 1
            schedule.last_run_at = now
            schedule.next_run_at = _next_run(schedule, now)
            schedule.save(update_fields=['last_run_at', 'next_run_at', 'updated_at'])
            run = ReportRun.objects.filter(schedule=schedule, status=ReportRun.Status.RUNNING).order_by('-created_at').first()
            if run:
                run.status = ReportRun.Status.FAILED
                run.error = str(exc)
                run.completed_at = timezone.now()
                run.save(update_fields=['status', 'error', 'completed_at', 'updated_at'])
    return {'due': len(due), 'delivered': delivered, 'failed': failed}

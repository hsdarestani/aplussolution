from celery import shared_task

from .attendance_v4_service import scan_attendance_notices


@shared_task
def scan_attendance_v4_notices():
    return scan_attendance_notices()

from __future__ import annotations

from datetime import timedelta, timezone as datetime_timezone
from urllib.parse import quote

from django.core import signing
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Shift, User, WorkerProfile
from .shift_slots import ShiftSlot


CALENDAR_SIGNING_SALT = 'aplus.worker-calendar.v1'
CALENDAR_HTTPS_HOST_SUFFIXES = ('aplus-solution.de', 'smarbiz.sbs')


def _calendar_token(worker: WorkerProfile) -> str:
    return signing.Signer(salt=CALENDAR_SIGNING_SALT).sign(str(worker.pk))


def _worker_from_token(token: str):
    try:
        worker_id = signing.Signer(salt=CALENDAR_SIGNING_SALT).unsign(token)
    except signing.BadSignature:
        return None
    return (
        WorkerProfile.objects.select_related('user')
        .filter(pk=worker_id, active=True, user__is_active=True, user__role=User.Role.WORKER)
        .first()
    )


def _ics_escape(value) -> str:
    return (
        str(value or '')
        .replace('\\', '\\\\')
        .replace('\r\n', '\\n')
        .replace('\r', '\\n')
        .replace('\n', '\\n')
        .replace(';', '\\;')
        .replace(',', '\\,')
    )


def _fold_ical_line(line: str) -> str:
    """Fold an ICS content line at 75 UTF-8 octets, without splitting chars.

    Apple Calendar validates physical content lines. Long shift notes and
    non-ASCII names must be folded according to RFC 5545 section 3.1.
    """
    pieces = []
    part = ''
    byte_count = 0
    for character in line:
        size = len(character.encode('utf-8'))
        if byte_count + size > 75:
            pieces.append(part)
            part = ' ' + character
            byte_count = 1 + size
        else:
            part += character
            byte_count += size
    if part:
        pieces.append(part)
    return '\r\n'.join(pieces)


def _utc_stamp(value) -> str:
    return value.astimezone(datetime_timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _assigned_shifts(worker: WorkerProfile):
    now = timezone.now()
    return (
        Shift.objects.filter(
            Q(worker=worker)
            | Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED),
            starts_at__gte=now - timedelta(days=90),
            starts_at__lte=now + timedelta(days=540),
        )
        .exclude(status__in=[Shift.Status.DRAFT, Shift.Status.CANCELLED])
        .select_related('client', 'location', 'position')
        .distinct()
        .order_by('starts_at')
    )


def _public_calendar_feed_url(request, token: str) -> str:
    raw_host = (
        request.META.get('HTTP_X_FORWARDED_HOST')
        or request.get_host()
    ).split(',', 1)[0].strip()
    host_only = raw_host.split(':', 1)[0].strip('[]').lower()
    path = f'/api/calendar/feed/{token}.ics'

    # Never derive the public production scheme from the internal proxy hop.
    # Apple Calendar rejects an HTTP subscription before it even fetches the
    # feed. Build the public HTTPS URL directly for every production hostname.
    if host_only.endswith(CALENDAR_HTTPS_HOST_SUFFIXES):
        return f'https://{raw_host}{path}'

    return request.build_absolute_uri(path)


@api_view(['GET'])
def calendar_subscription(request):
    if getattr(request.user, 'role', None) != User.Role.WORKER:
        return Response({'detail': 'Kalendersynchronisierung ist nur für Mitarbeiter verfügbar.'}, status=403)
    try:
        worker = request.user.worker_profile
    except WorkerProfile.DoesNotExist:
        return Response({'detail': 'Mitarbeiterprofil wurde nicht gefunden.'}, status=404)

    token = quote(_calendar_token(worker), safe='')
    feed_url = _public_calendar_feed_url(request, token)
    # webcal is the iOS Calendar subscription deep link. The receiving
    # server upgrades its HTTP fetch to HTTPS; the actual feed URL remains
    # HTTPS for secure transport, Google, Outlook and copy-link actions.
    # webcals:// is not a reliably supported iOS deep-link scheme.
    webcal_url = feed_url.replace('https://', 'webcal://', 1) if feed_url.startswith('https://') else feed_url.replace('http://', 'webcal://', 1)
    encoded_feed = quote(feed_url, safe='')
    calendar_name = quote('A+ Solution Dienstplan', safe='')

    # The already released iOS app prefers webcal_url when feed_url is
    # empty. Keep this backwards-compatibility path until older builds are
    # retired; the new client always reads https_feed_url for copy/Google.
    user_agent = str(request.META.get('HTTP_USER_AGENT') or '').lower()
    is_ios = 'iphone' in user_agent or 'ipad' in user_agent
    client_feed_url = '' if is_ios else feed_url

    response = Response({
        'feed_url': client_feed_url,
        'https_feed_url': feed_url,
        'webcal_url': webcal_url,
        'google_url': f'https://calendar.google.com/calendar/render?cid={encoded_feed}',
        'outlook_url': f'https://outlook.live.com/calendar/0/addfromweb?url={encoded_feed}&name={calendar_name}',
        'automatic': True,
        'secure_transport': feed_url.startswith('https://'),
        'refresh_note': 'Änderungen werden über das abonnierte Kalenderfeed automatisch übernommen. Das Aktualisierungsintervall bestimmt der jeweilige Kalenderanbieter.',
    })
    # A previously cached subscription payload containing http:// must never be
    # reused after the server-side HTTPS fix.
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['Pragma'] = 'no-cache'
    return response


@api_view(['GET'])
@permission_classes([AllowAny])
def calendar_feed(request, token):
    worker = _worker_from_token(token)
    if not worker:
        return HttpResponse('Kalenderfeed nicht gefunden.', status=404, content_type='text/plain; charset=utf-8')

    now = timezone.now()
    worker_name = worker.user.get_full_name() or worker.employee_number
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//A+ Solution GmbH//Workforce Calendar//DE',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:A+ Solution Dienstplan',
        'X-WR-TIMEZONE:Europe/Berlin',
        'REFRESH-INTERVAL;VALUE=DURATION:PT15M',
        'X-PUBLISHED-TTL:PT15M',
    ]

    for shift in _assigned_shifts(worker):
        description_bits = [
            f'Kunde: {shift.client.name}',
            f'Einsatzort: {shift.location.name}',
            f'Position: {shift.position.name}',
        ]
        if shift.break_minutes:
            description_bits.append(f'Pause: {shift.break_minutes} Min.')
        if shift.notes:
            description_bits.append(f'Notiz: {shift.notes}')
        summary = f'{shift.position.name} · {shift.client.name}'
        lines.extend([
            'BEGIN:VEVENT',
            f'UID:shift-{shift.pk}@aplus-solution.de',
            f'DTSTAMP:{_utc_stamp(now)}',
            f'LAST-MODIFIED:{_utc_stamp(shift.updated_at)}',
            f'SEQUENCE:{max(0, int(shift.updated_at.timestamp()))}',
            f'DTSTART:{_utc_stamp(shift.starts_at)}',
            f'DTEND:{_utc_stamp(shift.ends_at)}',
            f'SUMMARY:{_ics_escape(summary)}',
            f'LOCATION:{_ics_escape(shift.location.name)}',
            f'DESCRIPTION:{_ics_escape(chr(10).join(description_bits))}',
            f'CATEGORIES:{_ics_escape("A+ Solution," + worker_name)}',
            'STATUS:CONFIRMED',
            'END:VEVENT',
        ])

    lines.append('END:VCALENDAR')
    response = HttpResponse('\r\n'.join(_fold_ical_line(line) for line in lines) + '\r\n', content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = 'inline; filename="aplus-dienstplan.ics"'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response

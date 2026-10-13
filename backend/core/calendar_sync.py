from __future__ import annotations

from datetime import timedelta, timezone as datetime_timezone
from urllib.parse import quote, urlsplit

from django.core import signing
from django.db.models import Q
from django.http import HttpResponse
from django.utils.html import escape
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Shift, User, WorkerProfile
from .shift_slots import ShiftSlot


CALENDAR_SIGNING_SALT = 'aplus.worker-calendar.v1'
CALENDAR_HTTPS_HOST_SUFFIXES = ('aplus-solution.de', 'smarbiz.sbs')


def _calendar_token(worker: WorkerProfile) -> str:
    # The default Django Signer separator is a colon, which becomes %3A when
    # embedded in a calendar subscription URL. Some external calendar clients
    # rewrite or double-encode percent escapes. The tilde is RFC 3986-safe
    # in a URL path, so no percent escapes are needed for new subscriptions.
    return signing.Signer(salt=CALENDAR_SIGNING_SALT, sep='~').sign(str(worker.pk))


def _worker_from_token(token: str):
    # Existing subscriptions must keep working indefinitely. Fall back to
    # the legacy ":" format, including links saved before this change.
    worker_id = None
    for sep in ('~', ':'):
        try:
            worker_id = signing.Signer(salt=CALENDAR_SIGNING_SALT, sep=sep).unsign(token)
            break
        except signing.BadSignature:
            continue
    if worker_id is None:
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
    # Put new subscriptions on a clean, HTTPS-only endpoint. Old /api links
    # remain valid for existing subscribers and Google/Outlook bookmarks.
    path = (f'/calendar/{token}.ics' if host_only == 'app.aplus-solution.de'
            else f'/api/calendar/feed/{token}.ics')

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

    token = _calendar_token(worker)  # URL-safe: no percent encoding required.
    feed_url = _public_calendar_feed_url(request, token)
    # webcal is the iOS Calendar subscription deep link. The receiving
    # server upgrades its HTTP fetch to HTTPS; the actual feed URL remains
    # HTTPS for secure transport, Google, Outlook and copy-link actions.
    # webcals:// is not a reliably supported iOS deep-link scheme.
    webcal_url = feed_url.replace('https://', 'webcal://', 1) if feed_url.startswith('https://') else feed_url.replace('http://', 'webcal://', 1)
    encoded_feed = quote(feed_url, safe='')
    calendar_name = quote('A+ Solution Dienstplan', safe='')

    # Keep the same canonical HTTPS link for every platform. In particular,
    # emptying feed_url on iOS breaks the copy link fallback for subscribers.
    # Existing webcal_url is retained for older installed app versions.
    parsed_feed = urlsplit(feed_url)
    setup_url = f'{parsed_feed.scheme}://{parsed_feed.netloc}/calendar/subscribe/{token}'

    response = Response({
        'feed_url': feed_url,
        'apple_setup_url': setup_url,
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
def calendar_subscribe_page(request, token):
    """Safari handoff for a signed calendar subscription.

    A user initiated webcal link in Safari is an alternative to dispatching
    custom URL schemes directly from Capacitor's WKWebView. When iOS cannot
    complete the direct subscription, the HTTPS URL is always available for
    the system Calendar's Add Subscription Calendar flow.
    """
    worker = _worker_from_token(token)
    if worker is None:
        return HttpResponse('Kalenderlink nicht gefunden.', status=404, content_type='text/plain; charset=utf-8')

    secure_feed = _public_calendar_feed_url(request, token)
    if not secure_feed.startswith('https://'):
        return HttpResponse('Für dieses Kalenderabo ist HTTPS erforderlich.', status=400,
                            content_type='text/plain; charset=utf-8')
    deep_link = secure_feed.replace('https://', 'webcal://', 1)
    html = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>A+ Solution Kalender</title>
<style>
:root{color-scheme:light;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
body{background:#f3f6f9;color:#102c3e;margin:0;padding:32px 16px}
main{max-width:450px;background:white;margin:10vh auto 0;padding:28px 24px;
border-radius:18px;box-shadow:0 8px 32px #0b23351c}
h1{font-size:1.35rem;margin:0 0 16px}
p{font-size:.94rem;line-height:1.55}
a.button{display:block;background:#07324b;color:white;text-align:center;
font-weight:650;text-decoration:none;padding:15px 12px;border-radius:10px;margin-top:24px}
label{display:block;font-size:.84rem;margin:20px 0 6px}
input{box-sizing:border-box;width:100%;padding:12px 10px;border:1px solid #b9c7d2;
border-radius:8px;font-size:.92rem}
.note{font-size:.79rem;color:#455967}
</style>
</head>
<body><main>
<h1>Schichtplan in Apple Kalender</h1>
<p>Tippe auf <strong>Kalender abonnieren</strong> und bestätige das Abo in Apple Kalender. Änderungen deiner Schichten werden danach vom Kalender automatisch abgerufen.</p>
<a class="button" href="__WEBCAL__">Kalender abonnieren</a>
<p class="note">Falls Apple Kalender eine unsichere Verbindung meldet, wähle Abbrechen. Nutze dann in Apple Kalender die Funktion Kalender hinzufügen, Abo Kalender hinzufügen und füge die HTTPS Adresse unten ein.</p>
<label for="feed">Persönlicher HTTPS Kalenderlink</label>
<input id="feed" type="text" readonly value="__HTTPS__" onclick="this.select()" aria-label="Persönlicher HTTPS Kalenderlink">
<p class="note">Dieser Link ist privat. Teile ihn nicht mit anderen Personen. Die Aktualisierung kann je nach Apple Kalender einige Zeit dauern.</p>
</main></body></html>"""
    html = html.replace('__WEBCAL__', escape(deep_link)).replace('__HTTPS__', escape(secure_feed))
    response = HttpResponse(html, content_type='text/html; charset=utf-8')
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Content-Type-Options'] = 'nosniff'
    response['X-Frame-Options'] = 'DENY'
    response['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@api_view(['GET', 'HEAD'])
@permission_classes([AllowAny])
def calendar_compatibility_test(request):
    """Public synthetic iCalendar fixture, independent of SPA/frontend deploys.

    This contains no user data and deliberately serves the known-good test
    at a stable HTTPS URL to distinguish transport problems from worker feeds.
    """
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//A+ Solution GmbH//Calendar Compatibility Check//DE',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:A+ Solution Kalender Kompatibilitaetstest',
        'X-WR-TIMEZONE:Europe/Berlin',
        'BEGIN:VEVENT',
        'UID:calendar-compatibility-2027@aplus-solution.de',
        'DTSTAMP:20261013T170000Z',
        'DTSTART:20271005T100000Z',
        'DTEND:20271005T110000Z',
        'SUMMARY:A+ Solution Testtermin',
        'DESCRIPTION:Oeffentlicher Testeintrag ohne personenbezogene Daten',
        'END:VEVENT',
        'END:VCALENDAR',
    ]
    response = HttpResponse(
        '\r\n'.join(_fold_ical_line(line) for line in lines) + '\r\n',
        content_type='text/calendar; charset=utf-8',
    )
    response['Cache-Control'] = 'public, max-age=0, no-cache, must-revalidate'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@api_view(['GET', 'HEAD'])
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
    ]

    shifts = _assigned_shifts(worker)
    # Temporary, read-only Apple Calendar compatibility probe. It changes
    # only the output of an explicitly requested signed URL; existing
    # subscribed URLs continue to include every assigned shift.
    if request.query_params.get('qa_events') == '1':
        shifts = shifts[:1]

    for shift in shifts:
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
            f'DTSTART:{_utc_stamp(shift.starts_at)}',
            f'DTEND:{_utc_stamp(shift.ends_at)}',
            f'SUMMARY:{_ics_escape(summary)}',
            f'LOCATION:{_ics_escape(shift.location.name)}',
            f'DESCRIPTION:{_ics_escape(chr(10).join(description_bits))}',
            'END:VEVENT',
        ])

    lines.append('END:VCALENDAR')
    response = HttpResponse('\r\n'.join(_fold_ical_line(line) for line in lines) + '\r\n', content_type='text/calendar; charset=utf-8')
    # Match the proven-working subscription fixture: serve raw text/calendar,
    # not a downloadable attachment. Clients manage refresh intervals.
    response['Cache-Control'] = 'private, max-age=0, must-revalidate'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response

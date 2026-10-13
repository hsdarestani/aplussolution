/**
 * Appetize-only diagnostic of the actual worker calendar feed.
 *
 * Do not log the URL: the signed .ics path is a bearer secret.
 * This verifies the exact user subscription through the native WebView
 * rather than an anonymous placeholder request from CI.
 */
export async function diagnoseWorkerCalendarFeed(feedUrl: string): Promise<string> {
  let parsed: URL;
  try {
    parsed = new URL(feedUrl);
  } catch {
    throw new Error('Kalenderlink fehlt oder ist ungültig.');
  }
  if (parsed.protocol !== 'https:') {
    throw new Error('Der Kalenderlink muss HTTPS verwenden.');
  }
  if (parsed.hostname !== 'app.aplus-solution.de') {
    throw new Error('Unerwarteter Kalender-Server. Bitte Support kontaktieren.');
  }
  if (!/^\/api\/calendar\/feed\/[^/]+\.ics$/.test(parsed.pathname)) {
    throw new Error('Kalenderpfad ist ungültig.');
  }

  let response: Response;
  try {
    response = await fetch(parsed.toString(), { method: 'GET', cache: 'no-store', redirect: 'follow' });
  } catch {
    throw new Error('Kalenderfeed über HTTPS nicht erreichbar (Netzwerk, TLS oder CORS).');
  }
  if (!response.ok) {
    throw new Error(`Kalenderfeed antwortet mit HTTP ${response.status}.`);
  }
  const type = (response.headers.get('content-type') || '').toLowerCase();
  if (!type.startsWith('text/calendar')) {
    throw new Error(`Kein Kalenderinhalt erhalten (Content-Type: ${type || 'unbekannt'}).`);
  }
  const content = await response.text();
  if (!/^BEGIN:VCALENDAR\r?\n/.test(content) || !/\r?\nEND:VCALENDAR\r?\n?$/.test(content)) {
    throw new Error('Kalenderfeed enthält keinen vollständigen VCALENDAR-Inhalt.');
  }
  return 'Kalenderfeed erreichbar: HTTPS, HTTP 200, text/calendar und VCALENDAR gültig (Grundprüfung).';
}

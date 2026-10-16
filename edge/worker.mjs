/**
 * Optional Cloudflare edge safety net. NOT deployed by the app's STRATO pipeline.
 * Configure route app.aplus-solution.de/* separately when approved.
 * No KV, database writes, redirects, or deployment side effects.
 */
import maintenanceHtml from '../frontend/public/maintenance.html';

const ERROR_STATUSES = new Set([500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 530]);
const BYPASS = /^\/(?:api|admin|calendar|static|media|assets)(?:\/|$)/i;
let recentAvailability = { at: 0, ok: false };

function originRequest(url, accept = 'text/html') {
  return new Request(url, {
    method: 'GET',
    headers: { Accept: accept, 'Cache-Control': 'no-cache' },
    cache: 'no-store',
  });
}
function isHtmlNavigation(request, url) {
  if (request.method !== 'GET' || BYPASS.test(url.pathname)) return false;
  if (url.pathname === '/health/' || url.pathname.startsWith('/__aplus/')) return false;
  const accept = request.headers.get('accept') || '';
  const dest = request.headers.get('sec-fetch-dest') || '';
  return accept.includes('text/html') && (!dest || dest === 'document');
}
function maintenancePage(env) {
  const configured = String(env?.MAINTENANCE_UNTIL || '').trim();
  const until = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})$/.test(configured)
    && Number.isFinite(Date.parse(configured)) ? configured : '';
  const html = maintenanceHtml.replace(
    '<meta name="aplus-maintenance-until" content="">',
    '<meta name="aplus-maintenance-until" content="' + until + '">',
  );
  return new Response(html, {
    status: 503,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
      'Retry-After': '30',
      'X-Robots-Tag': 'noindex, nofollow',
      'X-Aplus-Fallback': 'edge',
    },
  });
}
async function availability(origin) {
  const now = Date.now();
  if (now - recentAvailability.at < 20000) return recentAvailability.ok;
  try {
    const [health, shell] = await Promise.all([
      fetch(originRequest(new URL('/health/', origin), 'application/json'), { signal: AbortSignal.timeout(7500) }),
      fetch(originRequest(new URL('/', origin)), { signal: AbortSignal.timeout(7500) }),
    ]);
    const data = health.ok ? await health.json() : null;
    const markup = shell.ok ? await shell.text() : '';
    const ok = data?.status === 'ok' && markup.includes('<div id="root"');
    recentAvailability = { at: now, ok };
    return ok;
  } catch {
    recentAvailability = { at: now, ok: false };
    return false;
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/__aplus/availability') {
      const ok = await availability(url.origin);
      return Response.json({ status: ok ? 'ok' : 'unavailable' }, {
        status: ok ? 200 : 503,
        headers: { 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': url.origin },
      });
    }
    if (!isHtmlNavigation(request, url)) return fetch(request);
    if (env?.MAINTENANCE_MODE === 'on') return maintenancePage(env);

    try {
      const originResponse = await fetch(request, { signal: AbortSignal.timeout(9000) });
      if (ERROR_STATUSES.has(originResponse.status)) return maintenancePage(env);
      return originResponse;
    } catch {
      return maintenancePage(env);
    }
  },
};

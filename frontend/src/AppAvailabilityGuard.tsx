import { useEffect, useState } from 'react';
import { Capacitor } from '@capacitor/core';
import './app-availability.css';

type Availability = 'normal' | 'offline' | 'unavailable';
const OUTAGE_EVENT = 'aplus-backend-possibly-unavailable';
const PING_MS = 60000;
const RECOVERY_MS = 30000;
const CONFIRM_MS = 6000;
const HEALTH_URL = Capacitor.isNativePlatform()
  ? 'https://app.aplus-solution.de/api/status/ready/'
  : '/api/status/ready/';

async function checkHealth() {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 7000);
  try {
    const response = await fetch(HEALTH_URL + '?availability=' + Date.now(), {
      method: 'GET',
      cache: 'no-store',
      credentials: 'omit',
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) return false;
    const data = await response.json();
    return data?.status === 'ok';
  } catch {
    return false;
  } finally {
    window.clearTimeout(timer);
  }
}

export default function AppAvailabilityGuard() {
  const [availability, setAvailability] = useState<Availability>('normal');
  const [working, setWorking] = useState(false);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let cancelled = false;
    let inflight = false;
    let failures = 0;
    let successes = 0;
    let status: Availability = 'normal';
    let nextConfirm: number | undefined;

    async function probe() {
      if (cancelled || inflight || document.visibilityState === 'hidden') return;
      inflight = true;
      const success = await checkHealth();
      inflight = false;
      if (cancelled) return;
      if (success) {
        failures = 0;
        successes += 1;
        if (status !== 'normal' && successes >= 2) {
          status = 'normal';
          setAvailability('normal');
          // Refresh just those enhancers that already handle the app resume event.
          // Never reload the whole app: there may be unsaved time entries or notes.
          window.dispatchEvent(new Event('aplus-app-resume'));
        }
        if (status !== 'normal' && successes < 2) nextConfirm = window.setTimeout(probe, CONFIRM_MS);
      } else {
        successes = 0;
        failures += 1;
        if (failures >= 2) {
          status = navigator.onLine === false ? 'offline' : 'unavailable';
          setAvailability(status);
        } else {
          nextConfirm = window.setTimeout(probe, CONFIRM_MS);
        }
      }
    }

    const signal = () => { void probe(); };
    const online = () => { void probe(); };
    const visible = () => { if (document.visibilityState === 'visible') void probe(); };
    let lastRoutineCheck = Date.now();
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      const interval = status === 'normal' ? PING_MS : RECOVERY_MS;
      if (Date.now() - lastRoutineCheck < interval) return;
      lastRoutineCheck = Date.now();
      void probe();
    }, RECOVERY_MS);
    // One low-cost heartbeat even if no API call occurs. Do not gate App rendering.
    const initial = window.setTimeout(probe, 12000);

    window.addEventListener(OUTAGE_EVENT, signal);
    window.addEventListener('online', online);
    document.addEventListener('visibilitychange', visible);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.clearTimeout(initial);
      if (nextConfirm !== undefined) window.clearTimeout(nextConfirm);
      window.removeEventListener(OUTAGE_EVENT, signal);
      window.removeEventListener('online', online);
      document.removeEventListener('visibilitychange', visible);
    };
  }, []);

  useEffect(() => {
    if (availability === 'normal') return;
    const interval = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(interval);
  }, [availability]);

  if (availability === 'normal') return null;

  const offline = availability === 'offline';
  // Only show a countdown when there is a real, explicitly provided ETA.
  // Unplanned failures have no trustworthy prediction.
  const eta = Date.parse(document.querySelector<HTMLMetaElement>('meta[name="aplus-maintenance-until"]')?.content || '');
  const remaining = Number.isFinite(eta) ? eta - now : -1;
  const etaLabel = remaining > 0
    ? 'Voraussichtlich noch ' + Math.ceil(remaining / 60000) + ' Min. (nicht garantiert)'
    : 'Automatische Prüfung im Hintergrund · keine verbindliche Rückkehrzeit verfügbar';
  return (
    <div className="aplus-availability" role="dialog" aria-modal="true" aria-labelledby="aplus-availability-title" data-testid="aplus-availability">
      <div className="aplus-availability-visual" aria-hidden="true">
        <span className="aplus-availability-brand">A<span>+</span></span>
        <div className="aplus-availability-orbit"><span className="aplus-availability-clock">◷</span></div>
        <span className="aplus-availability-brandline">A+ SOLUTION GMBH</span>
      </div>
      <div className="aplus-availability-content">
        <div className="aplus-availability-pill"><i aria-hidden="true" />{offline ? 'Verbindung unterbrochen' : 'Wir prüfen die Verfügbarkeit'}</div>
        <small className="aplus-availability-kicker">KURZE UNTERBRECHUNG</small>
        <h1 id="aplus-availability-title">{offline ? 'Keine Verbindung.' : <>Gleich wieder <em>für Sie da.</em></>}</h1>
        <p>{offline
          ? 'Bitte überprüfen Sie Ihre Internetverbindung. Sobald die App erreichbar ist, wird diese Meldung ausgeblendet.'
          : 'A+ Solution ist momentan nicht vollständig erreichbar. Wir kümmern uns darum. Die Statusanzeige verändert keine Schichten, Arbeitszeiten oder Dokumente.'}
        </p>
        <div className="aplus-availability-status" aria-live="polite">
          <small>AKTUELLER STATUS</small>
          <strong>{working ? 'Verbindung wird geprüft …' : offline ? 'Warten auf Internetverbindung' : 'Wiederherstellung wird geprüft'}</strong>
          <span>{etaLabel}</span>
          <div className="aplus-availability-sweep" aria-hidden="true"><i /></div>
        </div>
        <button
          type="button"
          className="aplus-availability-retry"
          disabled={working}
          onClick={async () => {
            setWorking(true);
            try {
              const first = await checkHealth();
              // A single success during an unstable recovery is insufficient.
              const second = first && await checkHealth();
              if (second) {
                window.dispatchEvent(new Event('aplus-app-resume'));
                setAvailability('normal');
              }
            } finally {
              setWorking(false);
            }
          }}
        >{working ? 'Bitte warten …' : 'Jetzt erneut prüfen'} <span aria-hidden="true">↻</span></button>
        <small className="aplus-availability-footer">A+ Solution GmbH · {new Intl.DateTimeFormat('de-DE', {timeZone:'Europe/Berlin',hour:'2-digit',minute:'2-digit'}).format(new Date(now))} Uhr</small>
      </div>
    </div>
  );
}

import React, { useEffect, useMemo, useState } from 'react';

type DegradedDetail = { path?: string; cached?: boolean };

function friendlyName(path: string) {
  if (path.includes('/document-catalog/')) return 'Dokumentvorlagen';
  if (path.includes('/working-time/')) return 'Arbeitszeitkonto';
  if (path.includes('/automation/orders/packages/')) return 'Auftragsautomation';
  if (path.includes('/integrations/wiw/status/')) return 'Migrationsstatus';
  if (path.includes('/operations/folders/')) return 'Digitale Akten';
  if (path.includes('/shifts/')) return 'Dienstplan-Entwürfe';
  return 'Steuerzentrale';
}

export default function ApiHealthBanner() {
  const [degraded, setDegraded] = useState<Record<string, DegradedDetail>>({});

  useEffect(() => {
    const failed = (event: Event) => {
      const detail = (event as CustomEvent<DegradedDetail>).detail || {};
      const path = detail.path || 'unknown';
      setDegraded((current) => ({ ...current, [path]: detail }));
    };
    const recovered = (event: Event) => {
      const detail = (event as CustomEvent<DegradedDetail>).detail || {};
      const path = detail.path || 'unknown';
      setDegraded((current) => {
        const next = { ...current };
        delete next[path];
        return next;
      });
    };
    window.addEventListener('aplus-api-degraded', failed);
    window.addEventListener('aplus-api-recovered', recovered);
    return () => {
      window.removeEventListener('aplus-api-degraded', failed);
      window.removeEventListener('aplus-api-recovered', recovered);
    };
  }, []);

  const rows = useMemo(() => Object.entries(degraded), [degraded]);
  if (!rows.length) return null;

  const labels = Array.from(new Set(rows.map(([path]) => friendlyName(path))));
  const hasCache = rows.some(([, detail]) => detail.cached);

  return (
    <div className="aplus-api-health" role="status" aria-live="polite">
      <b>Ein Teil der Daten ist vorübergehend nicht erreichbar.</b>
      <span>
        {labels.join(', ')}: {hasCache ? 'letzter verfügbarer Stand wird angezeigt.' : 'neutraler Fallback wird angezeigt.'}
        {' '}Andere Bereiche bleiben weiter nutzbar.
      </span>
      <button type="button" onClick={() => window.location.reload()}>Erneut laden</button>
    </div>
  );
}

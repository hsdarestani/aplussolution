import React, { useEffect, useRef, useState } from 'react';
import { IonIcon, IonSpinner } from '@ionic/react';
import {
  briefcaseOutline,
  businessOutline,
  calendarOutline,
  closeOutline,
  documentTextOutline,
  peopleOutline,
  searchOutline,
} from 'ionicons/icons';
import { api } from './api';
import './global-search.css';

type Result = {
  type: string;
  id: string;
  label: string;
  subtitle: string;
  view: string;
  status?: string;
  meta?: Record<string, any>;
};

const typeLabel: Record<string, string> = {
  worker: 'Mitarbeiter',
  client: 'Kunde',
  order: 'Auftrag',
  shift: 'Schicht',
  contract: 'Vertrag',
};

const typeIcon: Record<string, string> = {
  worker: peopleOutline,
  client: businessOutline,
  order: briefcaseOutline,
  shift: calendarOutline,
  contract: documentTextOutline,
};

const isMigrationOnlyResult = (result: Result) =>
  result.type === 'worker' && `${result.label || ''} ${result.subtitle || ''}`.toLowerCase().includes('@sync.invalid');

export default function GlobalSearch({ onNavigate }: { onNavigate: (view: any) => void }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [data, setData] = useState<any>();
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen(true);
      } else if (event.key === '/' && !typing) {
        event.preventDefault();
        setOpen(true);
      } else if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', keydown);
    return () => window.removeEventListener('keydown', keydown);
  }, []);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => inputRef.current?.focus(), 40);
    return () => window.clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (query.trim().length < 2) {
      setData(undefined);
      setBusy(false);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setBusy(true);
      try {
        const result = await api(`search/global/?q=${encodeURIComponent(query.trim())}&limit=6`);
        if (!cancelled) setData(result);
      } finally {
        if (!cancelled) setBusy(false);
      }
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query]);

  const select = (result: Result) => {
    sessionStorage.setItem('aplus:focus', JSON.stringify({ view: result.view, id: result.id, type: result.type, query }));
    setOpen(false);
    setQuery('');
    setData(undefined);
    onNavigate(result.view);
  };

  const results: Result[] = (data?.results || []).filter((result: Result) => !isMigrationOnlyResult(result));

  return (
    <>
      <button type="button" className="global-search-trigger" onClick={() => setOpen(true)} data-testid="global-search-trigger">
        <IonIcon icon={searchOutline} />
        <span>Mitarbeiter, Kunde, Auftrag, Schicht oder Vertrag suchen …</span>
        <kbd>⌘ K</kbd>
      </button>

      {open && (
        <div className="global-search-backdrop" role="dialog" aria-modal="true" aria-label="Globale Suche" onMouseDown={(event) => event.target === event.currentTarget && setOpen(false)}>
          <section className="global-search-dialog">
            <div className="global-search-input-wrap">
              <IonIcon icon={searchOutline} />
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Name, Kundennummer, Auftrag, Ort, Position oder Vertrag …"
                aria-label="Globale Suche"
              />
              {busy ? <IonSpinner name="crescent" /> : query ? <button type="button" onClick={() => setQuery('')} aria-label="Suche leeren"><IonIcon icon={closeOutline} /></button> : null}
            </div>

            <div className="global-search-body">
              {query.trim().length < 2 && (
                <div className="global-search-hint">
                  <strong>Mindestens zwei Zeichen eingeben.</strong>
                  <span>Du kannst nach Mitarbeiter, Kunde, Auftrag, Einsatz oder Vertrag suchen.</span>
                </div>
              )}

              {query.trim().length >= 2 && !busy && !results.length && (
                <div className="global-search-hint"><strong>Keine Treffer.</strong><span>Versuche einen anderen Namen, Ort oder Begriff.</span></div>
              )}

              {!!results.length && (
                <div className="global-search-results">
                  {results.map((result) => (
                    <button type="button" key={`${result.type}-${result.id}`} onClick={() => select(result)}>
                      <span className="global-result-icon"><IonIcon icon={typeIcon[result.type] || searchOutline} /></span>
                      <span className="global-result-copy">
                        <small>{typeLabel[result.type] || result.type}</small>
                        <strong>{result.label}</strong>
                        <span>{result.subtitle}</span>
                      </span>
                      {result.status && <em>{result.status}</em>}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <footer className="global-search-footer"><span>Enter: öffnen</span><span>Esc: schließen</span><span>/ : suchen</span></footer>
          </section>
        </div>
      )}
    </>
  );
}

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from './api';
import './wiw-shift-form-ux.css';

const NOTE_TEMPLATES: Array<{ id: string; title: string; body: string }> = [
  { id: 'uniform', title: 'Arbeitskleidung', body: 'Bitte pünktlich erscheinen und auf vollständige, saubere Arbeitskleidung achten.' },
  { id: 'contact', title: 'Vor Ort melden', body: 'Bitte 10 Minuten vor Einsatzbeginn vor Ort sein und sich bei der Einsatzleitung melden.' },
  { id: 'documents', title: 'Unterlagen mitbringen', body: 'Bitte Ausweis und alle für den Einsatz erforderlichen Unterlagen mitbringen.' },
  { id: 'hotel', title: 'Hotel · schwarze Kleidung', body: 'Bitte gepflegte schwarze Kleidung und schwarze, geschlossene Schuhe tragen.' },
];

type Client = { id: string; name: string; active?: boolean };

type LocationDraft = {
  name: string;
  address: string;
  geofence_radius_m: number;
};

function text(value: Element | null) {
  return String(value?.textContent || '').replace(/\s+/g, ' ').trim();
}

function unpack(value: any): any[] {
  return value?.results || value || [];
}

function findForm() {
  return document.querySelector<HTMLElement>('.wiw-shift-form-screen');
}

function formScroll() {
  return findForm()?.querySelector<HTMLElement>('.wiw-form-scroll') || null;
}

function directActionRows() {
  const scroll = formScroll();
  if (!scroll) return [] as HTMLButtonElement[];
  return Array.from(scroll.children).filter((node): node is HTMLButtonElement => node instanceof HTMLButtonElement && node.matches('.wiw-form-row'));
}

function locationRow() {
  return findForm()?.querySelector<HTMLButtonElement>('[data-field="location"]') || null;
}

function clientRow() {
  return findForm()?.querySelector<HTMLButtonElement>('[data-field="client"]') || null;
}

function noteRow() {
  return directActionRows().find((row) => /Notiz|Hinweis/.test(text(row))) || null;
}

function decorateStandardColorRow() {
  const rows = Array.from(findForm()?.querySelectorAll<HTMLElement>('.wiw-form-row') || []);
  const row = rows.find((item) => text(item).includes('Standardfarbe'));
  if (!row || row.dataset.colorManaged === 'true') return;
  row.classList.add('wiw-standard-color-row');
  row.setAttribute('aria-label', 'Standardfarbe: A+ Navy, automatisch');
  row.setAttribute('title', 'Die Schichtfarbe folgt automatisch dem A+ Navy Design.');
  const copy = row.querySelector<HTMLElement>('.wiw-form-row-copy');
  if (!copy || copy.querySelector('.wiw-standard-color-hint')) return;
  const hint = document.createElement('b');
  hint.className = 'wiw-standard-color-hint';
  const swatch = document.createElement('i');
  swatch.className = 'wiw-standard-color-swatch';
  swatch.setAttribute('aria-hidden', 'true');
  const label = document.createElement('span');
  label.textContent = 'A+ Navy · automatisch';
  hint.append(swatch, label);
  copy.appendChild(hint);
}

function setNativeTextareaValue(value: string) {
  const ensureTextarea = () => {
    const textarea = findForm()?.querySelector<HTMLTextAreaElement>('.wiw-extra-options textarea');
    if (textarea) {
      const descriptor = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
      descriptor?.set?.call(textarea, value);
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      textarea.dispatchEvent(new Event('change', { bubbles: true }));
      textarea.focus();
      return true;
    }
    const row = noteRow();
    if (row && !findForm()?.querySelector('.wiw-extra-options')) row.click();
    return false;
  };

  if (ensureTextarea()) return;
  window.setTimeout(ensureTextarea, 80);
}

function selectedClient(clients: Client[]) {
  const label = text(clientRow());
  if (!label || label === 'Kunde auswählen') return undefined;
  return clients.find((client) => client.name.trim() === label.trim());
}

async function waitForAndSelectLocation(name: string) {
  locationRow()?.click();
  for (let attempt = 0; attempt < 25; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 160));
    const sheet = Array.from(document.querySelectorAll<HTMLElement>('.wiw-choice-sheet')).find((node) => text(node.querySelector('header b')) === 'Jobstandort');
    const choice = sheet ? Array.from(sheet.querySelectorAll<HTMLButtonElement>(':scope > div > button')).find((button) => text(button) === name) : undefined;
    if (choice) {
      choice.click();
      return true;
    }
  }
  return false;
}

export default function WiwShiftFormUxEnhancer() {
  const [open, setOpen] = useState(false);
  const [scrollHost, setScrollHost] = useState<HTMLElement | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [locationOpen, setLocationOpen] = useState(false);
  const [locationDraft, setLocationDraft] = useState<LocationDraft>({ name: '', address: '', geofence_radius_m: 250 });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(''), 1000);
    return () => window.clearTimeout(timer);
  }, [message]);

  useEffect(() => {
    const sync = () => {
      const currentForm = findForm();
      const isOpen = Boolean(currentForm);
      setOpen(isOpen);
      setScrollHost(currentForm?.querySelector<HTMLElement>('.wiw-form-scroll') || null);
      document.body.classList.toggle('wiw-shift-form-active', isOpen);
      if (isOpen) window.setTimeout(decorateStandardColorRow, 0);
      if (!isOpen) {
        setTemplateOpen(false);
        setLocationOpen(false);
        setMessage('');
      }
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      document.body.classList.remove('wiw-shift-form-active');
    };
  }, []);

  useEffect(() => {
    if (!open || clients.length) return;
    api('clients/').then((data: any) => {
      setClients(unpack(data).filter((item: Client) => item.active !== false));
    }).catch(() => undefined);
  }, [open, clients.length]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (!templateOpen && !locationOpen) return;
      event.preventDefault();
      if (templateOpen) setTemplateOpen(false);
      if (locationOpen) setLocationOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, templateOpen, locationOpen]);

  async function saveLocation() {
    const client = selectedClient(clients);
    if (!client) {
      setMessage('Bitte zuerst einen Kunden auswählen.');
      return;
    }
    if (!locationDraft.name.trim() || !locationDraft.address.trim()) {
      setMessage('Bitte Bezeichnung und Adresse ausfüllen.');
      return;
    }

    setBusy(true);
    try {
      const saved: any = await api('locations/', {
        method: 'POST',
        body: JSON.stringify({
          client: client.id,
          name: locationDraft.name.trim(),
          address: locationDraft.address.trim(),
          geofence_radius_m: Math.max(25, Number(locationDraft.geofence_radius_m || 250)),
          active: true,
        }),
      });
      setLocationOpen(false);
      const savedName = String(saved?.name || locationDraft.name);
      setLocationDraft({ name: '', address: '', geofence_radius_m: 250 });

      document.querySelector<HTMLButtonElement>('.wiw-search-row button')?.click();
      const selected = await waitForAndSelectLocation(savedName);
      setMessage(selected ? 'Einsatzort gespeichert und ausgewählt.' : 'Einsatzort gespeichert. Bitte Jobstandort einmal öffnen und auswählen.');
    } catch (error: any) {
      setMessage(error.message || 'Einsatzort konnte nicht gespeichert werden.');
    } finally {
      setBusy(false);
    }
  }

  if (!open || typeof document === 'undefined') return null;
  const client = selectedClient(clients);

  const inlineExtras = scrollHost ? createPortal(
    <div className="wiw-form-extra-actions" aria-label="Zusätzliche Schichtoptionen">
      <div className="wiw-form-separator" />
      <button type="button" onClick={() => setLocationOpen(true)} disabled={!client}>
        <span className="wiw-extra-icon">⌖</span>
        <span><b>Einsatzort anlegen</b><small>{client ? `für ${client.name}` : 'Zuerst Kunde auswählen'}</small></span>
        <em>›</em>
      </button>
      <button type="button" onClick={() => setTemplateOpen(true)}>
        <span className="wiw-extra-icon">≡</span>
        <span><b>Textvorlage für Notiz</b><small>Mitarbeiterhinweis schnell einsetzen</small></span>
        <em>›</em>
      </button>
    </div>,
    scrollHost,
  ) : null;

  const overlays = createPortal(
    <>
      {templateOpen ? <div className="wiw-enhancer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setTemplateOpen(false); }}>
        <section className="wiw-enhancer-sheet">
          <header><b>Textvorlage für Mitarbeiterhinweis</b><button type="button" onClick={() => setTemplateOpen(false)}>Fertig</button></header>
          <div className="wiw-template-list">
            {NOTE_TEMPLATES.map((template) => <button type="button" key={template.id} onClick={() => { setNativeTextareaValue(template.body); setTemplateOpen(false); setMessage('Textvorlage übernommen.'); }}>
              <b>{template.title}</b><span>{template.body}</span>
            </button>)}
          </div>
        </section>
      </div> : null}

      {locationOpen ? <div className="wiw-enhancer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setLocationOpen(false); }}>
        <section className="wiw-enhancer-sheet wiw-location-create-sheet">
          <header><b>Einsatzort anlegen</b><button type="button" onClick={() => setLocationOpen(false)}>Abbrechen</button></header>
          <div className="wiw-enhancer-form">
            <div className="wiw-client-context"><small>Kunde</small><strong>{client?.name || 'Bitte zuerst Kunde auswählen'}</strong></div>
            <label>Bezeichnung<input autoFocus value={locationDraft.name} onChange={(event) => setLocationDraft((current) => ({ ...current, name: event.target.value }))} placeholder="z. B. Haupteingang / Hotel / Saal" /></label>
            <label>Adresse<textarea value={locationDraft.address} onChange={(event) => setLocationDraft((current) => ({ ...current, address: event.target.value }))} placeholder="Straße, Hausnummer, PLZ, Ort" /></label>
            <label>Geofence-Radius<input type="number" min="25" step="25" value={locationDraft.geofence_radius_m} onChange={(event) => setLocationDraft((current) => ({ ...current, geofence_radius_m: Number(event.target.value) }))} /></label>
          </div>
          <div className="wiw-enhancer-actions"><button type="button" onClick={() => setLocationOpen(false)}>Abbrechen</button><button type="button" className="primary" disabled={busy || !client} onClick={() => void saveLocation()}>{busy ? 'Speichert …' : 'Speichern & auswählen'}</button></div>
        </section>
      </div> : null}

      {message ? <button type="button" className="wiw-enhancer-message" onClick={() => setMessage('')}>{message}</button> : null}
    </>,
    document.body,
  );

  return <>{inlineExtras}{overlays}</>;
}

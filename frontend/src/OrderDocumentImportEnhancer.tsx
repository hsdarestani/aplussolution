import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  IonBadge,
  IonButton,
  IonCheckbox,
  IonIcon,
  IonModal,
  IonSelect,
  IonSelectOption,
  IonSpinner,
} from '@ionic/react';
import { cloudUploadOutline, documentTextOutline, sparklesOutline } from 'ionicons/icons';
import { api } from './api';
import './order-document-import.css';

type ClientRow = { id: string; name: string; customer_number?: string };
type ParsedShift = {
  role: string;
  date: string;
  start_time: string;
  end_time: string;
  count: number;
  location_text?: string;
  site_text?: string;
  notes?: string;
};
type ParsedOrder = {
  request_id: string;
  contract_no: string;
  source_status: string;
  source_page: number;
  title?: string;
  organizer?: string;
  raw_text: string;
  shifts: ParsedShift[];
};
type ParseResult = {
  file_name: string;
  page_count: number;
  order_count: number;
  shift_count: number;
  staff_slots: number;
  orders: ParsedOrder[];
};

type ImportResult = {
  status: string;
  imported_orders: number;
  published_orders: number;
  draft_orders: number;
  created_staff_slots: number;
  errors?: Array<{ request_id: string; detail: string }>;
};

const unpack = (data: any): any[] => data?.results || data || [];
const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9äöüß]+/g, ' ').trim();

export default function OrderDocumentImportEnhancer() {
  const [target, setTarget] = useState<Element | null>(null);
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File>();
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [clientId, setClientId] = useState('');
  const [parsed, setParsed] = useState<ParseResult>();
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [imported, setImported] = useState<ImportResult>();

  useEffect(() => {
    const locate = () => {
      const panel = document.querySelector('[data-testid="order-automation-panel"]');
      const actions = panel?.querySelector('.operations-actions') || null;
      setTarget((current) => (current === actions ? current : actions));
    };
    locate();
    const observer = new MutationObserver(locate);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!open || clients.length) return;
    void api('clients/?ordering=name')
      .then((data: any) => {
        const rows = unpack(data) as ClientRow[];
        setClients(rows);
        if (!clientId) {
          const martha = rows.find((item) => normalize(item.name).includes('martha'));
          if (martha) setClientId(martha.id);
        }
      })
      .catch((error: any) => setMessage(error.message || 'Kunden konnten nicht geladen werden.'));
  }, [open, clients.length, clientId]);

  const selectedOrders = useMemo(
    () => (parsed?.orders || []).filter((order) => selected[order.request_id] !== false),
    [parsed, selected],
  );

  function reset() {
    setFile(undefined);
    setParsed(undefined);
    setSelected({});
    setMessage('');
    setImported(undefined);
  }

  function close() {
    setOpen(false);
    reset();
  }

  async function analyze() {
    if (!file) {
      setMessage('Bitte zuerst die Personal-/Bestellliste auswählen.');
      return;
    }
    setBusy(true);
    setMessage('');
    setImported(undefined);
    try {
      const form = new FormData();
      form.append('file', file);
      const result = await api<ParseResult>('automation/orders/parse-file/', { method: 'POST', body: form });
      setParsed(result);
      const next: Record<string, boolean> = {};
      result.orders.forEach((order) => { next[order.request_id] = true; });
      setSelected(next);
      setMessage(`${result.order_count} Aufträge und ${result.shift_count} Schichten erkannt. Bitte kurz prüfen.`);
    } catch (error: any) {
      setMessage(error.message || 'Die Datei konnte nicht analysiert werden.');
    } finally {
      setBusy(false);
    }
  }

  async function importOrders() {
    if (!clientId) {
      setMessage('Bitte zuerst den Kunden auswählen – für diese Liste z. B. Marthas Finest.');
      return;
    }
    if (!selectedOrders.length) {
      setMessage('Bitte mindestens einen Auftrag auswählen.');
      return;
    }
    setBusy(true);
    setMessage('');
    try {
      const result = await api<ImportResult>('automation/orders/approve-file/', {
        method: 'POST',
        body: JSON.stringify({ client_id: clientId, orders: selectedOrders }),
      });
      setImported(result);
      const suffix = result.errors?.length ? ` · ${result.errors.length} Auftrag/Aufträge prüfen` : '';
      setMessage(`${result.published_orders} definitive Aufträge veröffentlicht, ${result.draft_orders} Optionen als Entwurf angelegt${suffix}.`);
    } catch (error: any) {
      setMessage(error.message || 'Die Aufträge konnten nicht übernommen werden.');
    } finally {
      setBusy(false);
    }
  }

  const button = target ? createPortal(
    <IonButton fill="outline" onClick={() => setOpen(true)} data-testid="order-document-import-button">
      <IonIcon slot="start" icon={cloudUploadOutline} />
      Datei mit AI einlesen
    </IonButton>,
    target,
  ) : null;

  return (
    <>
      {button}
      <IonModal isOpen={open} onDidDismiss={close} cssClass="order-document-import-modal">
        <div className="order-import-shell">
          <header className="order-import-header">
            <div className="order-import-kicker"><IonIcon icon={sparklesOutline} /> A+ AI PLANUNG</div>
            <h2>Personal-Bestellliste importieren</h2>
            <p>PDF, DOCX oder TXT einlesen, alle Veranstaltungen als einzelne Aufträge erkennen und vor der Übernahme gemeinsam prüfen.</p>
          </header>

          <div className="order-import-body">
            <section className="order-import-source">
              <label className="order-import-file">
                <IonIcon icon={documentTextOutline} />
                <span><b>{file?.name || 'Bestellliste auswählen'}</b><small>PDF, DOCX oder TXT · max. 15 MB</small></span>
                <input
                  type="file"
                  accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                  onChange={(event) => {
                    setFile(event.target.files?.[0]);
                    setParsed(undefined);
                    setImported(undefined);
                    setSelected({});
                    setMessage('');
                  }}
                />
              </label>

              <div className="order-import-client">
                <label>Kunde / Planung</label>
                <IonSelect
                  interface="popover"
                  placeholder="Kunde auswählen"
                  value={clientId}
                  onIonChange={(event) => setClientId(String(event.detail.value || ''))}
                >
                  {clients.map((client) => (
                    <IonSelectOption key={client.id} value={client.id}>
                      {client.name}{client.customer_number ? ` · ${client.customer_number}` : ''}
                    </IonSelectOption>
                  ))}
                </IonSelect>
                <small>Damit alle Einsätze dieser Liste z. B. unter „Marthas Finest“ landen und nicht als neue Kunden angelegt werden.</small>
              </div>
            </section>

            {!parsed && (
              <div className="order-import-empty">
                <IonIcon icon={sparklesOutline} />
                <b>Die bestehende AI-Auftragsautomation kann jetzt auch ganze Dateien lesen.</b>
                <span>Jede Veranstaltungs-Nr. wird getrennt. Mehrtägige Einsätze und mehrere Personalzeilen bleiben erhalten.</span>
              </div>
            )}

            {parsed && (
              <>
                <div className="order-import-summary">
                  <span><b>{parsed.page_count}</b> Seiten</span>
                  <span><b>{parsed.order_count}</b> Aufträge</span>
                  <span><b>{parsed.shift_count}</b> Schichten</span>
                  <span><b>{parsed.staff_slots}</b> Personalplätze</span>
                </div>
                <div className="order-import-legend">
                  <IonBadge color="success">Definitiv → veröffentlicht</IonBadge>
                  <IonBadge color="warning">Option/unklar → Entwurf</IonBadge>
                  <span>Nichts wird vor dem Klick auf „Ausgewählte übernehmen“ in den Dienstplan geschrieben.</span>
                </div>
                <div className="order-import-list">
                  {parsed.orders.map((order) => {
                    const definitive = normalize(order.source_status) === 'definitiv';
                    return (
                      <article className="order-import-card" key={order.request_id}>
                        <div className="order-import-card-head">
                          <IonCheckbox
                            checked={selected[order.request_id] !== false}
                            onIonChange={(event) => setSelected({ ...selected, [order.request_id]: event.detail.checked })}
                          />
                          <div>
                            <b>#{order.request_id}{order.title ? ` · ${order.title}` : ''}</b>
                            <small>Seite {order.source_page}{order.organizer ? ` · ${order.organizer}` : ''}</small>
                          </div>
                          <IonBadge color={definitive ? 'success' : 'warning'}>{order.source_status || 'Unklar'}</IonBadge>
                        </div>
                        <div className="order-import-shifts">
                          {order.shifts.map((shift, index) => (
                            <div key={`${order.request_id}-${index}`}>
                              <b>{shift.date} · {shift.start_time}–{shift.end_time}</b>
                              <span>{shift.count}× {shift.role}{shift.location_text ? ` · ${shift.location_text}` : ''}</span>
                              {shift.notes && <small>{shift.notes}</small>}
                            </div>
                          ))}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </>
            )}

            {message && <div className={`order-import-message ${imported?.errors?.length ? 'warning' : ''}`}>{message}</div>}
            {!!imported?.errors?.length && (
              <div className="order-import-errors">
                {imported.errors.map((error) => <div key={error.request_id}><b>#{error.request_id}</b> {error.detail}</div>)}
              </div>
            )}
          </div>

          <footer className="order-import-footer">
            <IonButton fill="clear" onClick={close}>Schließen</IonButton>
            {imported ? (
              <IonButton onClick={() => window.location.reload()}>Dienstplan aktualisieren</IonButton>
            ) : parsed ? (
              <IonButton disabled={busy || !selectedOrders.length || !clientId} onClick={importOrders}>
                {busy ? <IonSpinner name="dots" /> : `Ausgewählte übernehmen (${selectedOrders.length})`}
              </IonButton>
            ) : (
              <IonButton disabled={busy || !file} onClick={analyze}>
                {busy ? <IonSpinner name="dots" /> : <><IonIcon slot="start" icon={sparklesOutline} />Mit AI analysieren</>}
              </IonButton>
            )}
          </footer>
        </div>
      </IonModal>
    </>
  );
}

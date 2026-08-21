import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, type User } from './api';
import './workflow-completion.css';

type EntityKind = 'worker' | 'client';
type Target = { kind: EntityKind; id: string; element: HTMLElement; label: string };

type AkteData = {
  kind: EntityKind;
  title: string;
  number: string;
  summary: Record<string, number>;
  contracts: any[];
  document_folders: { key: string; label: string; count: number; items: any[] }[];
  payroll?: any[];
  orders?: any[];
  locations?: any[];
  shifts?: any[];
};

const unpack = (value: any) => value?.results || value || [];
const date = (value?: string) => value ? new Date(value).toLocaleDateString('de-DE') : '–';
const dateTime = (value?: string) => value ? new Date(value).toLocaleString('de-DE') : '–';

function findTitle(texts: string[]) {
  return Array.from(document.querySelectorAll<HTMLElement>('.title h1')).find((node) => texts.includes((node.textContent || '').trim()))?.closest<HTMLElement>('.title') || null;
}

function findPanel(title: string) {
  return Array.from(document.querySelectorAll<HTMLElement>('.panel')).find((panel) =>
    (panel.querySelector('h3')?.textContent || '').trim() === title,
  ) || null;
}

function entityTargets(workers: any[], clients: any[]) {
  const output: Target[] = [];
  const workerPanel = findPanel('Mitarbeiter');
  const clientPanel = findPanel('Kunden');

  if (workerPanel) {
    workerPanel.querySelectorAll<HTMLElement>('.row').forEach((row) => {
      if (row.dataset.akteTarget === '1') return;
      const text = row.textContent || '';
      const worker = workers.find((item) => item.employee_number && text.includes(item.employee_number));
      if (!worker) return;
      row.dataset.akteTarget = '1';
      output.push({ kind: 'worker', id: worker.id, element: row, label: worker.user_detail?.name || worker.employee_number });
    });
  }

  if (clientPanel) {
    clientPanel.querySelectorAll<HTMLElement>('.row').forEach((row) => {
      if (row.dataset.akteTarget === '1') return;
      const text = row.textContent || '';
      const client = clients.find((item) => item.customer_number && text.includes(item.customer_number));
      if (!client) return;
      row.dataset.akteTarget = '1';
      output.push({ kind: 'client', id: client.id, element: row, label: client.name || client.customer_number });
    });
  }
  return output;
}

function FileModal({ data, close }: { data: AkteData; close: () => void }) {
  const summaryLabels: Record<string, string> = {
    contracts: 'Verträge',
    documents: 'Dokumente',
    payroll: 'Lohnabrechnungen',
    orders: 'Aufträge',
    locations: 'Einsatzorte',
    shifts: 'Einsätze',
  };

  return createPortal(
    <div className="akte-overlay" role="dialog" aria-modal="true" aria-label={`${data.title} Akte`} data-testid="akte-modal">
      <div className="akte-modal">
        <div className="akte-head">
          <div>
            <small>{data.kind === 'worker' ? 'MITARBEITERAKTE' : 'KUNDENAKTE'} · {data.number}</small>
            <h2>{data.title}</h2>
            <p>Alle Verträge, Dokumente und zugeordneten Vorgänge an einem Ort.</p>
          </div>
          <button type="button" onClick={close} aria-label="Akte schließen">Schließen</button>
        </div>

        <div className="akte-summary">
          {Object.entries(data.summary || {}).map(([key, count]) => (
            <div key={key}><span>{summaryLabels[key] || key}</span><strong>{count}</strong></div>
          ))}
        </div>

        <div className="akte-sections">
          <section>
            <h3>Verträge</h3>
            {(data.contracts || []).map((contract) => (
              <div className="akte-row" key={contract.id}>
                <div><b>{contract.title}</b><small>{contract.template_name} · {contract.status} · {date(contract.updated_at)}</small></div>
                {contract.pdf ? <a href={contract.pdf} target="_blank" rel="noreferrer">PDF öffnen</a> : <span>Noch kein PDF</span>}
              </div>
            ))}
            {!data.contracts?.length && <p className="akte-empty">Noch keine Verträge.</p>}
          </section>

          {(data.document_folders || []).map((folder) => (
            <section key={folder.key}>
              <h3>{folder.label} <em>{folder.count}</em></h3>
              {folder.items.map((document) => (
                <div className="akte-row" key={document.id}>
                  <div><b>{document.title}</b><small>{date(document.created_at)} · {document.visibility}</small></div>
                  <a href={document.file} target="_blank" rel="noreferrer">Öffnen</a>
                </div>
              ))}
            </section>
          ))}

          {data.kind === 'worker' && (
            <section>
              <h3>Lohnabrechnungen</h3>
              {(data.payroll || []).map((statement) => (
                <div className="akte-row" key={statement.id}>
                  <div><b>{date(statement.period)}</b><small>{statement.gross_amount ? `Brutto ${statement.gross_amount} €` : 'Abrechnung'}</small></div>
                  <a href={statement.document} target="_blank" rel="noreferrer">PDF öffnen</a>
                </div>
              ))}
              {!data.payroll?.length && <p className="akte-empty">Noch keine Lohnabrechnungen.</p>}
            </section>
          )}

          {data.kind === 'client' && (
            <>
              <section>
                <h3>Aufträge</h3>
                {(data.orders || []).map((order) => (
                  <div className="akte-row" key={order.id}>
                    <div><b>{order.title}</b><small>{dateTime(order.starts_at)} · {order.requested_staff} Personen</small></div>
                    {order.attachment ? <a href={order.attachment} target="_blank" rel="noreferrer">Datei öffnen</a> : <span>Ohne Datei</span>}
                  </div>
                ))}
                {!data.orders?.length && <p className="akte-empty">Noch keine Aufträge.</p>}
              </section>
              <section>
                <h3>Einsatzorte</h3>
                {(data.locations || []).map((location) => (
                  <div className="akte-row" key={location.id}><div><b>{location.name}</b><small>{location.address}</small></div><span>{location.geofence_radius_m} m</span></div>
                ))}
              </section>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

function OrderUploadModal({ close, orders, reload }: { close: () => void; orders: any[]; reload: () => Promise<void> }) {
  const [orderId, setOrderId] = useState(orders[0]?.id || '');
  const [note, setNote] = useState('');
  const [file, setFile] = useState<File>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const selected = useMemo(() => orders.find((order) => order.id === orderId), [orders, orderId]);

  async function upload() {
    if (!orderId || !file) {
      setMessage('Bitte Auftrag und Datei auswählen.');
      return;
    }
    setBusy(true);
    setMessage('');
    try {
      const body = new FormData();
      body.append('attachment', file);
      if (note.trim()) {
        const existing = String(selected?.description || '').trim();
        body.append('description', [existing, note.trim()].filter(Boolean).join('\n\n'));
      }
      await api(`orders/${orderId}/`, { method: 'PATCH', body });
      await reload();
      setMessage('Auftragsdatei wurde hochgeladen und dem Auftrag zugeordnet.');
      setFile(undefined);
      setNote('');
    } catch (error: any) {
      setMessage(error?.message || 'Datei konnte nicht hochgeladen werden.');
    } finally {
      setBusy(false);
    }
  }

  return createPortal(
    <div className="akte-overlay" role="dialog" aria-modal="true" aria-label="Auftragsdatei hochladen" data-testid="order-upload-modal">
      <div className="order-upload-modal">
        <div className="akte-head">
          <div><small>KUNDENPORTAL</small><h2>Auftrag / Functions hochladen</h2><p>Datei direkt dem bestehenden Auftrag zuordnen.</p></div>
          <button type="button" onClick={close}>Schließen</button>
        </div>
        <label>Auftrag
          <select aria-label="Auftrag auswählen" value={orderId} onChange={(event) => setOrderId(event.target.value)}>
            {orders.map((order) => <option key={order.id} value={order.id}>{order.title} · {date(order.starts_at)}</option>)}
          </select>
        </label>
        {!orders.length && <div className="workflow-note">Noch kein Auftrag vorhanden. Lege zuerst über „Neuer Auftrag“ die Veranstaltung an.</div>}
        {selected?.attachment && <div className="workflow-note">Bereits hochgeladen: <a href={selected.attachment} target="_blank" rel="noreferrer">aktuelle Auftragsdatei öffnen</a></div>}
        <label>Zusätzliche Functions / Hinweise
          <textarea aria-label="Functions und Hinweise" rows={4} value={note} onChange={(event) => setNote(event.target.value)} placeholder="z. B. 4 Service, 2 Runner, Dresscode …" />
        </label>
        <label className="order-file">Datei
          <input data-testid="order-file-input" type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.png,.jpg,.jpeg" onChange={(event) => setFile(event.target.files?.[0])} />
          <span>{file?.name || 'PDF, Word, Excel/CSV oder Bild auswählen'}</span>
        </label>
        {message && <div className="workflow-message" role="status">{message}</div>}
        <div className="workflow-actions">
          <button type="button" onClick={close}>Abbrechen</button>
          <button type="button" className="primary" disabled={busy || !orders.length} onClick={() => void upload()}>{busy ? 'Wird hochgeladen …' : 'Datei hochladen'}</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export default function WorkflowCompletionEnhancer() {
  const [user, setUser] = useState<User>();
  const [workers, setWorkers] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [akte, setAkte] = useState<AkteData>();
  const [loadingAkte, setLoadingAkte] = useState(false);
  const [orderTarget, setOrderTarget] = useState<HTMLElement | null>(null);
  const [orders, setOrders] = useState<any[]>([]);
  const [orderOpen, setOrderOpen] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    api<User>('auth/me/').then((current) => { if (!cancelled) setUser(current); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!user || !['admin', 'manager'].includes(user.role)) return;
    Promise.all([api('workers/?ordering=user__last_name'), api('clients/?ordering=name')])
      .then(([workerResponse, clientResponse]) => {
        setWorkers(unpack(workerResponse));
        setClients(unpack(clientResponse));
      })
      .catch(() => undefined);
  }, [user]);

  useEffect(() => {
    const scan = () => {
      if (user && ['admin', 'manager'].includes(user.role)) {
        const found = entityTargets(workers, clients);
        if (found.length) setTargets((current) => [...current.filter((item) => document.body.contains(item.element)), ...found]);
      }
      setOrderTarget(user?.role === 'client' ? findTitle(['Aufträge']) : null);
    };
    scan();
    const observer = new MutationObserver(scan);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [user, workers, clients]);

  async function openAkte(target: Target) {
    setLoadingAkte(true);
    setMessage('');
    try {
      setAkte(await api(`${target.kind === 'worker' ? 'workers' : 'clients'}/${target.id}/akte/`));
    } catch (error: any) {
      setMessage(error?.message || 'Akte konnte nicht geladen werden.');
    } finally {
      setLoadingAkte(false);
    }
  }

  async function loadOrders() {
    const response = await api('orders/?ordering=-starts_at');
    setOrders(unpack(response));
  }

  async function openOrderUpload() {
    try {
      await loadOrders();
      setOrderOpen(true);
    } catch (error: any) {
      setMessage(error?.message || 'Aufträge konnten nicht geladen werden.');
    }
  }

  return (
    <>
      {targets.map((target) => createPortal(
        <button
          key={`${target.kind}-${target.id}`}
          type="button"
          className="akte-open-button"
          data-testid={`akte-open-${target.kind}-${target.id}`}
          disabled={loadingAkte}
          onClick={() => void openAkte(target)}
          title={`${target.label} – digitale Akte öffnen`}
        >
          Akte
        </button>,
        target.element,
      ))}

      {orderTarget && createPortal(
        <button type="button" className="order-upload-button" data-testid="order-upload-open" onClick={() => void openOrderUpload()}>
          Auftrag / Functions hochladen
        </button>,
        orderTarget,
      )}

      {akte && <FileModal data={akte} close={() => setAkte(undefined)} />}
      {orderOpen && <OrderUploadModal close={() => setOrderOpen(false)} orders={orders} reload={loadOrders} />}
      {message && createPortal(<div className="workflow-global-message" role="status" onClick={() => setMessage('')}>{message}</div>, document.body)}
    </>
  );
}
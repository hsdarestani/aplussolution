import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, apiBlob } from './api';
import { saveSchedulePdf } from './saveSchedulePdf';
import { openPdfDocument } from './openPdfDocument';
import './shift-plan-attachments.css';

type Plan = {
  id: string;
  document_id?: string;
  name: string;
  event_numbers?: string[];
  event_dates?: string[];
  created_at?: string;
  visibility?: 'all' | 'worker';
  target_worker_id?: string | null;
  target_worker_name?: string;
  view_url?: string;
  download_url: string;
  delete_url?: string;
};

type BulkCandidate = {
  id: string;
  client_name?: string;
  location_name?: string;
  position_name?: string;
  starts_at?: string;
  ends_at?: string;
  score?: number;
  reason?: string;
};

type BulkResult = {
  name: string;
  status: 'matched' | 'needs_review' | 'error';
  detail?: string;
  document?: { id: string; event_numbers?: string[]; event_dates?: string[] };
  matched?: BulkCandidate[];
  candidates?: BulkCandidate[];
};

const TZ = 'Europe/Berlin';

function planPath(value: string) {
  return String(value || '').replace(/^\/?api\//, '').replace(/^\//, '');
}

function shortDate(value?: string) {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat('de-DE', {
      timeZone: TZ,
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
    }).format(new Date(value));
  } catch {
    return '';
  }
}

function shortTime(value?: string) {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat('de-DE', {
      timeZone: TZ,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(new Date(value));
  } catch {
    return '';
  }
}

function usefulPlace(candidate: BulkCandidate) {
  const location = String(candidate.location_name || '').trim();
  const normalized = location.toLocaleLowerCase('de-DE').replace(/[.]/g, '').trim();
  const placeholders = new Set(['siehe notiz', 's notiz', 'notiz', 'siehe bemerkung']);
  if (location && !placeholders.has(normalized)) return location;
  return candidate.client_name || 'Einsatz';
}

function shiftLabel(candidate: BulkCandidate) {
  const date = shortDate(candidate.starts_at);
  const start = shortTime(candidate.starts_at);
  const end = shortTime(candidate.ends_at);
  const time = start && end ? start + ' bis ' + end : start;
  const place = usefulPlace(candidate);
  const customer = candidate.client_name && candidate.client_name !== place ? candidate.client_name : '';
  const position = candidate.position_name || '';
  return [date, time, customer, place, position].filter(Boolean).join(' · ');
}

async function shareOrSavePlan(plan: Plan) {
  const result = await apiBlob(planPath(plan.download_url));
  await saveSchedulePdf(result.blob, result.filename || plan.name || 'Einsatzplan.pdf', 'Einsatzplan');
}

export function ShiftPlanAttachments({
  shift,
  canUpload = false,
  compact = false,
  onChanged,
}: {
  shift: any;
  canUpload?: boolean;
  compact?: boolean;
  onChanged?: () => void | Promise<void>;
}) {
  const [plans, setPlans] = useState<Plan[]>(Array.isArray(shift?.plans) ? shift.plans : []);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [pendingFile, setPendingFile] = useState<File>();
  const [visibility, setVisibility] = useState<'all' | 'worker'>('all');
  const [targetWorker, setTargetWorker] = useState('');
  const [preview, setPreview] = useState<{ plan: Plan; url: string }>();
  const [previewZoom, setPreviewZoom] = useState(1);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setPlans(Array.isArray(shift?.plans) ? shift.plans : []);
  }, [shift?.id, shift?.plans]);

  useEffect(() => {
    if (!preview) return;
    const previousOverflow = document.body.style.overflow;
    document.body.classList.add('shift-plan-preview-open');
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closePreview();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.classList.remove('shift-plan-preview-open');
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [preview?.url]);

  async function upload(file?: File) {
    if (!file || !shift?.id || busy) return;
    if (visibility === 'worker' && !targetWorker) {
      setMessage('Bitte einen Mitarbeiter auswählen.');
      return;
    }
    setBusy(true);
    setMessage('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('visibility', visibility);
      if (visibility === 'worker') form.append('target_worker', targetWorker);
      const saved: Plan = await api(`shifts/${shift.id}/plans/`, { method: 'POST', body: form });
      setPlans((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      setMessage('Einsatzplan hinzugefügt.');
      setPendingFile(undefined);
      setVisibility('all');
      setTargetWorker('');
      await onChanged?.();
    } catch (error: any) {
      setMessage(error?.message || 'Einsatzplan konnte nicht hochgeladen werden.');
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  }

  async function openPreview(plan: Plan) {
    if (busy) return;
    setBusy(true);
    setMessage('');
    try {
      const result = await apiBlob(planPath(plan.view_url || plan.download_url));
      // Present PDF using iOS native document viewer, outside the app shell.
      // Keep the browser-only iframe fallback for desktop web users.
      if (await openPdfDocument(result.blob, result.filename || plan.name)) return;
      const url = URL.createObjectURL(result.blob);
      setPreviewZoom(1);
      setPreview((current) => {
        if (current?.url) URL.revokeObjectURL(current.url);
        return { plan, url };
      });
    } catch (error: any) {
      setMessage(error?.message || 'Einsatzplan konnte nicht geöffnet werden.');
    } finally {
      setBusy(false);
    }
  }

  function closePreview() {
    setPreviewZoom(1);
    setPreview((current) => {
      if (current?.url) URL.revokeObjectURL(current.url);
      return undefined;
    });
  }

  function changePreviewZoom(delta: number) {
    setPreviewZoom((current) => Math.max(0.75, Math.min(3, Math.round((current + delta) * 100) / 100)));
  }

  async function removePlan(plan: Plan) {
    if (!plan.delete_url || busy) return;
    if (!window.confirm('Einsatzplan wirklich löschen?')) return;
    setBusy(true);
    setMessage('');
    try {
      await api(planPath(plan.delete_url), { method: 'DELETE' });
      setPlans((current) => current.filter((item) => item.id !== plan.id));
      if (preview?.plan.id === plan.id) closePreview();
      setMessage('Einsatzplan gelöscht.');
      await onChanged?.();
    } catch (error: any) {
      setMessage(error?.message || 'Einsatzplan konnte nicht gelöscht werden.');
    } finally {
      setBusy(false);
    }
  }

  if (compact && !plans.length) return null;
  return <div className={`shift-plan-box ${compact ? 'compact' : ''}`} onClick={(event) => event.stopPropagation()}>
    <div className="shift-plan-head">
      <span><b>Einsatzplan</b>{plans.length > 0 ? <small>{plans.length} PDF</small> : <small>Noch kein Plan</small>}</span>
      {canUpload && !compact ? <button type="button" disabled={busy} onClick={() => input.current?.click()}>{busy ? 'Lädt…' : 'PDF hinzufügen'}</button> : null}
    </div>
    <input
      ref={input}
      type="file"
      accept="application/pdf,.pdf"
      hidden
      onChange={(event) => {
        const file = event.target.files?.[0];
        setPendingFile(file || undefined);
        setVisibility('all');
        setTargetWorker('');
      }}
    />
    {pendingFile && canUpload && !compact ? <div className="shift-plan-scope">
      <b>Für wen ist dieser Einsatzplan?</b>
      <div className="shift-plan-scope-options">
        <button type="button" className={visibility === 'all' ? 'active' : ''} onClick={() => { setVisibility('all'); setTargetWorker(''); }}>
          Alle Mitarbeiter der Schicht
        </button>
        <button type="button" className={visibility === 'worker' ? 'active' : ''} onClick={() => setVisibility('worker')}>
          Nur ein Mitarbeiter
        </button>
      </div>
      {visibility === 'worker' ? <select value={targetWorker} onChange={(event) => setTargetWorker(event.target.value)}>
        <option value="">Mitarbeiter auswählen</option>
        {(Array.isArray(shift?.assigned_workers) ? shift.assigned_workers : []).map((worker: any) => (
          <option value={worker.id} key={worker.id}>{worker.name || worker.employee_number || 'Mitarbeiter'}</option>
        ))}
      </select> : null}
      <div className="shift-plan-scope-actions">
        <button type="button" onClick={() => { setPendingFile(undefined); if (input.current) input.current.value = ''; }}>Abbrechen</button>
        <button type="button" className="primary" disabled={busy || (visibility === 'worker' && !targetWorker)} onClick={() => void upload(pendingFile)}>
          {busy ? 'Lädt…' : 'Hochladen'}
        </button>
      </div>
    </div> : null}
    {plans.length ? <div className="shift-plan-list">
      {plans.map((plan) => <div className="shift-plan-file" key={plan.id} title={plan.name}>
        <button type="button" className="shift-plan-file-main" onClick={() => void openPreview(plan)}>
          <span className="shift-plan-file-icon">PDF</span>
          <span>
            <b>{plan.name}</b>
            <small>
              {plan.visibility === 'worker' && plan.target_worker_name
                ? `Nur für ${plan.target_worker_name}`
                : plan.event_numbers?.length
                  ? `Event ${plan.event_numbers.join(', ')}`
                  : 'In der App ansehen'}
            </small>
          </span>
          <em>›</em>
        </button>
        {canUpload && !compact && plan.delete_url ? <button type="button" className="shift-plan-delete" disabled={busy} onClick={() => void removePlan(plan)} aria-label="Einsatzplan löschen">Löschen</button> : null}
      </div>)}
    </div> : null}
    {preview ? createPortal(<div
      className="shift-plan-preview"
      role="dialog"
      aria-modal="true"
      aria-label={preview.plan.name}
      onClick={(event) => event.stopPropagation()}
    >
      <div className="shift-plan-preview-card">
        <div className="shift-plan-preview-head">
          <b>{preview.plan.name}</b>
          <div className="shift-plan-preview-head-actions">
            <div className="shift-plan-preview-zoom" aria-label="PDF Zoom">
              <button type="button" onClick={() => changePreviewZoom(-0.25)} disabled={previewZoom <= 0.75} aria-label="Verkleinern">−</button>
              <button type="button" className="shift-plan-preview-zoom-value" onClick={() => setPreviewZoom(1)} aria-label="Zoom zurücksetzen">
                {Math.round(previewZoom * 100)}%
              </button>
              <button type="button" onClick={() => changePreviewZoom(0.25)} disabled={previewZoom >= 3} aria-label="Vergrößern">+</button>
            </div>
            <button
              type="button"
              className="shift-plan-preview-close"
              onPointerDown={(event) => {
                event.preventDefault();
                event.stopPropagation();
                closePreview();
              }}
              aria-label="Schließen"
            >×</button>
          </div>
        </div>
        <div className="shift-plan-preview-stage">
          <iframe
            src={preview.url}
            title={preview.plan.name}
            style={{ width: `${previewZoom * 100}%`, height: `${previewZoom * 100}%` }}
          />
        </div>
        <div className="shift-plan-preview-actions">
          <button type="button" onPointerDown={(event) => { event.preventDefault(); closePreview(); }}>Schließen</button>
          <button type="button" className="primary" onClick={() => void shareOrSavePlan(preview.plan)}>Speichern / Teilen</button>
        </div>
      </div>
    </div>, document.body) : null}
    {message && !compact ? <small className="shift-plan-message">{message}</small> : null}
  </div>;
}

export function ShiftPlanBulkUpload({
  onChanged,
  label = 'Pläne hochladen',
}: {
  onChanged?: () => void | Promise<void>;
  label?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<BulkResult[]>([]);
  const [message, setMessage] = useState('');
  const [expanded, setExpanded] = useState(false);

  async function upload(files?: FileList | null) {
    if (!files?.length || busy) return;
    setBusy(true);
    setMessage('');
    setResults([]);
    try {
      const form = new FormData();
      Array.from(files).forEach((file) => form.append('files', file));
      const response: any = await api('shift-plans/bulk-upload/', { method: 'POST', body: form });
      const nextResults: BulkResult[] = Array.isArray(response?.files) ? response.files : [];
      setResults(nextResults);
      const matched = Number(response?.matched_attachments || 0);
      const review = Number(response?.needs_review || 0);
      const errors = Number(response?.errors || 0);
      const parts = [
        matched === 1 ? '1 Schicht automatisch zugeordnet.' : matched > 1 ? matched + ' Schichten automatisch zugeordnet.' : 'Noch keine Schicht automatisch zugeordnet.',
        review ? (review === 1 ? '1 Datei bitte prüfen.' : review + ' Dateien bitte prüfen.') : '',
        errors ? (errors === 1 ? '1 Datei konnte nicht verarbeitet werden.' : errors + ' Dateien konnten nicht verarbeitet werden.') : '',
      ].filter(Boolean);
      setMessage(parts.join(' '));
      setExpanded(review > 0 || errors > 0);
      await onChanged?.();
    } catch (error: any) {
      setMessage(error?.message || 'Einsatzpläne konnten nicht verarbeitet werden.');
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  }

  async function attach(resultIndex: number, documentId: string, candidate: BulkCandidate) {
    setBusy(true);
    setMessage('');
    try {
      await api(`shift-plans/documents/${documentId}/attach/`, {
        method: 'POST',
        body: JSON.stringify({ shift: candidate.id }),
      });
      setResults((current) => current.map((item, index) => index === resultIndex
        ? { ...item, status: 'matched', matched: [...(item.matched || []), candidate] }
        : item));
      setMessage('Plan wurde der Schicht zugeordnet.');
      setExpanded(true);
      await onChanged?.();
    } catch (error: any) {
      setMessage(error?.message || 'Plan konnte nicht zugeordnet werden.');
    } finally {
      setBusy(false);
    }
  }

  const needsAttention = results.some((item) => item.status !== 'matched');
  const uploadLabel = label === 'Einsatzpläne' || label === 'Pläne' ? 'PDFs hochladen' : label;

  return <section className="shift-plan-bulk" onClick={(event) => event.stopPropagation()}>
    <div className="shift-plan-bulk-head">
      <div className="shift-plan-bulk-heading">
        <span className="shift-plan-bulk-doc" aria-hidden="true">PDF</span>
        <span>
          <b>Einsatzpläne</b>
          <small>PDFs automatisch den passenden Schichten zuordnen</small>
        </span>
      </div>
      <button type="button" className="shift-plan-bulk-button" disabled={busy} onClick={() => input.current?.click()}>
        {busy ? 'Prüfung läuft…' : uploadLabel}
      </button>
    </div>

    <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(event) => void upload(event.target.files)} />

    {message ? <div className={'shift-plan-bulk-message ' + (needsAttention ? 'attention' : 'success')}>
      <span className="shift-plan-bulk-state" aria-hidden="true">{needsAttention ? '!' : '✓'}</span>
      <span>{message}</span>
      {results.length ? <button type="button" className="shift-plan-details-toggle" onClick={() => setExpanded((value) => !value)}>
        {expanded ? 'Weniger' : 'Details'}
      </button> : null}
    </div> : null}

    {expanded && results.length ? <div className="shift-plan-bulk-results">
      {results.map((item, index) => <div className={'shift-plan-result ' + item.status} key={item.name + '-' + index}>
        <div className="shift-plan-result-head">
          <div className="shift-plan-result-file">
            <span className="shift-plan-result-file-icon">PDF</span>
            <span>
              <b title={item.name}>{item.name}</b>
              <small>{item.document?.event_numbers?.length ? 'Event ' + item.document.event_numbers.join(', ') : 'Einsatzplan'}</small>
            </span>
          </div>
          <span className="shift-plan-result-status">
            {item.status === 'matched' ? 'Zugeordnet' : item.status === 'error' ? 'Fehler' : 'Prüfen'}
          </span>
        </div>

        {item.matched?.length ? <div className="shift-plan-result-shifts">
          {item.matched.map((candidate) => <span key={candidate.id}>
            <i aria-hidden="true">✓</i>
            {shiftLabel(candidate)}
          </span>)}
        </div> : null}

        {item.detail ? <small className="shift-plan-result-detail">{item.detail}</small> : null}

        {item.status === 'needs_review' && item.document?.id && item.candidates?.length ? <div className="shift-plan-candidates">
          <small>Passende Schicht auswählen</small>
          {item.candidates.map((candidate) => <button
            type="button"
            disabled={busy}
            key={candidate.id}
            onClick={() => void attach(index, item.document!.id, candidate)}
            title={candidate.reason || ''}
          >
            <span>{shiftLabel(candidate)}</span>
            {candidate.score ? <em>Treffer {candidate.score}</em> : null}
          </button>)}
        </div> : null}
      </div>)}
    </div> : null}
  </section>;
}

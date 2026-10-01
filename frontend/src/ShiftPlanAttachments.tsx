import React, { useEffect, useRef, useState } from 'react';
import { api, apiBlob } from './api';
import { saveSchedulePdf } from './saveSchedulePdf';
import './shift-plan-attachments.css';

type Plan = {
  id: string;
  document_id?: string;
  name: string;
  event_numbers?: string[];
  event_dates?: string[];
  created_at?: string;
  download_url: string;
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

async function downloadPlan(plan: Plan) {
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
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setPlans(Array.isArray(shift?.plans) ? shift.plans : []);
  }, [shift?.id, shift?.plans]);

  async function upload(file?: File) {
    if (!file || !shift?.id || busy) return;
    setBusy(true);
    setMessage('');
    try {
      const form = new FormData();
      form.append('file', file);
      const saved: Plan = await api(`shifts/${shift.id}/plans/`, { method: 'POST', body: form });
      setPlans((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      setMessage('Einsatzplan hinzugefügt.');
      await onChanged?.();
    } catch (error: any) {
      setMessage(error?.message || 'Einsatzplan konnte nicht hochgeladen werden.');
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
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
      onChange={(event) => void upload(event.target.files?.[0])}
    />
    {plans.length ? <div className="shift-plan-list">
      {plans.map((plan) => <button
        type="button"
        className="shift-plan-file"
        key={plan.id}
        onClick={() => void downloadPlan(plan)}
        title={plan.name}
      >
        <span className="shift-plan-file-icon">PDF</span>
        <span><b>{plan.name}</b><small>{plan.event_numbers?.length ? `Event ${plan.event_numbers.join(', ')}` : 'Plan herunterladen'}</small></span>
        <em>↓</em>
      </button>)}
    </div> : null}
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

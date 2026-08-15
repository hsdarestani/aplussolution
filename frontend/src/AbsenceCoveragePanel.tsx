import React, { useEffect, useMemo, useState } from 'react';
import {
  IonBadge,
  IonButton,
  IonCheckbox,
  IonIcon,
  IonInput,
  IonModal,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonToast,
} from '@ionic/react';
import { alertCircleOutline, checkmarkCircleOutline, peopleOutline, refreshOutline } from 'ionicons/icons';
import { api, apiAll, User } from './api';
import './absence-coverage.css';

const val = (e: any) => e.detail.value ?? '';
const isManager = (user: User) => ['admin', 'manager'].includes(user.role);
const dateTime = (input?: string) => input ? new Date(input).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' }) : '–';
const activeStatuses = new Set(['reported', 'coverage_pending', 'offered', 'moved_to_open']);
const kindLabels: Record<string, string> = {
  sick: 'Krank', emergency: 'Notfall', personal: 'Persönlich verhindert', no_show: 'Nicht erschienen',
  approved_time_off: 'Genehmigte Abwesenheit', other: 'Sonstiger Ausfall',
};
const statusLabels: Record<string, string> = {
  reported: 'Gemeldet', coverage_pending: 'Ersatz offen', offered: 'Angebote versendet', moved_to_open: 'OpenShift',
  covered: 'Abgedeckt', resolved_uncovered: 'Ohne Ersatz geschlossen', cancelled: 'Storniert',
};

export default function AbsenceCoveragePanel({ user, onChanged }: { user: User; onChanged?: () => void | Promise<void> }) {
  if (user.role === 'client') return null;
  const manager = isManager(user);
  const [cases, setCases] = useState<any[]>([]);
  const [offers, setOffers] = useState<any[]>([]);
  const [shifts, setShifts] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [reportOpen, setReportOpen] = useState(false);
  const [report, setReport] = useState<any>({ kind: manager ? 'no_show' : 'sick' });
  const [candidateCase, setCandidateCase] = useState<any>();
  const [candidates, setCandidates] = useState<any[]>([]);
  const [selectedCandidates, setSelectedCandidates] = useState<Set<string>>(new Set());
  const [offerHours, setOfferHours] = useState(12);

  async function load() {
    try {
      const [caseRows, shiftRows, offerRows] = await Promise.all([
        apiAll(manager ? 'absence-cases/?ordering=-reported_at' : 'absence-cases/?ordering=-reported_at'),
        apiAll(manager ? 'shifts/?ordering=starts_at' : 'shifts/mine/?ordering=starts_at'),
        manager ? Promise.resolve([]) : apiAll('coverage-offers/?ordering=-offered_at'),
      ]);
      setCases(caseRows);
      setShifts(shiftRows);
      setOffers(offerRows);
    } catch (error: any) {
      setToast(error.message);
    }
  }

  useEffect(() => { void load(); }, []);

  async function mutate(path: string, payload: any, success: string) {
    setBusy(true);
    try {
      const result = await api(path, { method: 'POST', body: JSON.stringify(payload) });
      setToast(success);
      await load();
      await onChanged?.();
      return result;
    } catch (error: any) {
      setToast(error.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  const reportOptions = useMemo(() => {
    const now = Date.now() - 12 * 60 * 60 * 1000;
    if (!manager) return shifts.filter((shift) => new Date(shift.ends_at).getTime() >= now).map((shift) => ({
      key: `${shift.id}`,
      shift: shift.id,
      worker: undefined,
      slot: shift.assignments?.find((item: any) => item.mine)?.slot || shift.assignments?.[0]?.slot,
      label: `${dateTime(shift.starts_at)} · ${shift.position_name} · ${shift.location_name}`,
    }));
    return shifts.flatMap((shift) => (shift.assignments || []).map((assignment: any) => ({
      key: `${shift.id}-${assignment.slot}`,
      shift: shift.id,
      worker: assignment.worker,
      slot: assignment.slot,
      label: `${dateTime(shift.starts_at)} · ${assignment.worker_name} · ${shift.position_name}`,
    }))).filter((item) => item.worker);
  }, [shifts, manager]);

  async function submitReport() {
    const option = reportOptions.find((item) => item.key === report.option);
    if (!option) { setToast('Bitte eine belegte Schicht auswählen.'); return; }
    const result = await mutate('operations/callouts/report/', {
      shift: option.shift,
      worker: option.worker,
      slot: option.slot,
      kind: report.kind,
      note: report.note || '',
    }, 'Ausfall wurde erfasst.');
    if (result) { setReportOpen(false); setReport({ kind: manager ? 'no_show' : 'sick' }); }
  }

  async function openCandidates(item: any) {
    setCandidateCase(item);
    setCandidates([]);
    setSelectedCandidates(new Set());
    try {
      const result: any = await api(`absence-cases/${item.id}/candidates/`);
      setCandidates(result.workers || []);
    } catch (error: any) { setToast(error.message); }
  }

  async function sendOffers() {
    if (!candidateCase || !selectedCandidates.size) { setToast('Mindestens einen Mitarbeiter auswählen.'); return; }
    const result = await mutate(`absence-cases/${candidateCase.id}/offer/`, {
      workers: [...selectedCandidates], expires_in_hours: offerHours,
    }, 'Ersatzanfragen wurden versendet.');
    if (result) setCandidateCase(undefined);
  }

  async function direct(candidate: any) {
    if (!candidateCase) return;
    const result = await mutate(`absence-cases/${candidateCase.id}/replace/`, { worker: candidate.worker }, 'Ersatz wurde direkt eingeplant.');
    if (result) setCandidateCase(undefined);
  }

  const activeCases = cases.filter((item) => activeStatuses.has(item.status));
  const shortNotice = activeCases.filter((item) => item.short_notice).length;
  const pendingOffers = offers.filter((item) => item.status === 'pending');

  return <section className="absence-workspace" data-testid="absence-coverage-panel">
    <div className="absence-head">
      <div><small>AUSFALL & ERSATZ</small><h3>{manager ? 'Callouts & Personalabdeckung' : 'Ausfall melden & Ersatzanfragen'}</h3><p>{manager ? 'Kurzfristige Ausfälle erfassen, geeignete Ersatzkräfte finden oder den Platz als OpenShift freigeben.' : 'Eigene Ausfälle früh melden und gezielte Ersatzanfragen beantworten.'}</p></div>
      <div className="absence-head-actions"><IonButton fill="outline" size="small" onClick={() => void load()}><IonIcon slot="start" icon={refreshOutline}/>Aktualisieren</IonButton><IonButton size="small" onClick={() => setReportOpen(true)}>{manager ? 'Ausfall erfassen' : 'Ausfall melden'}</IonButton></div>
    </div>

    <div className="absence-stats">
      <div><small>Offene Ausfälle</small><strong>{activeCases.length}</strong></div>
      <div><small>≤ 24 Stunden</small><strong>{shortNotice}</strong></div>
      <div><small>{manager ? 'Mit Angeboten' : 'Meine Ersatzanfragen'}</small><strong>{manager ? activeCases.filter((item) => item.open_offer_count > 0).length : pendingOffers.length}</strong></div>
      <div><small>Abgedeckt</small><strong>{cases.filter((item) => item.status === 'covered').length}</strong></div>
    </div>

    {!manager && pendingOffers.length > 0 && <div className="absence-offers">
      <h4>Offene Ersatzanfragen</h4>
      {pendingOffers.map((offer) => <article key={offer.id} className="absence-offer-card">
        <IonIcon icon={peopleOutline}/><div><b>{offer.shift_title}</b><p>{dateTime(offer.shift_starts_at)} · {offer.location_name}</p><small>Antwort bis {dateTime(offer.expires_at)}</small></div>
        <div className="absence-row-actions"><IonButton disabled={busy} size="small" color="success" onClick={() => void mutate(`coverage-offers/${offer.id}/respond/`, { status: 'accepted' }, 'Ersatzschicht übernommen.')}>Annehmen</IonButton><IonButton disabled={busy} size="small" fill="outline" color="medium" onClick={() => void mutate(`coverage-offers/${offer.id}/respond/`, { status: 'declined' }, 'Anfrage abgelehnt.')}>Ablehnen</IonButton></div>
      </article>)}
    </div>}

    <div className="absence-list">
      {cases.map((item) => <article className={`absence-case ${item.short_notice && activeStatuses.has(item.status) ? 'urgent' : ''}`} key={item.id}>
        <div className="absence-case-icon"><IonIcon icon={activeStatuses.has(item.status) ? alertCircleOutline : checkmarkCircleOutline}/></div>
        <div className="absence-case-main"><div className="absence-case-line"><b>{manager ? item.absent_worker_name : item.shift_title}</b>{item.short_notice && <IonBadge color="danger">Kurzfristig</IonBadge>}<IonBadge color={item.status === 'covered' ? 'success' : activeStatuses.has(item.status) ? 'warning' : 'medium'}>{statusLabels[item.status] || item.status}</IonBadge></div><p>{dateTime(item.shift_starts_at)} – {dateTime(item.shift_ends_at)} · {item.location_name}</p><small>{kindLabels[item.kind] || item.kind}{manager && item.reason_note ? ` · ${item.reason_note}` : ''}{item.replacement_worker_name ? ` · Ersatz: ${item.replacement_worker_name}` : ''}</small></div>
        {activeStatuses.has(item.status) && <div className="absence-row-actions">
          {manager ? <><IonButton size="small" onClick={() => void openCandidates(item)}>Ersatz finden</IonButton><IonButton size="small" fill="outline" onClick={() => void mutate(`absence-cases/${item.id}/move-to-open/`, {}, 'Platz wurde als OpenShift freigegeben.')}>OpenShift</IonButton><IonButton size="small" fill="clear" color="medium" onClick={() => void mutate(`absence-cases/${item.id}/resolve-uncovered/`, {}, 'Ausfall wurde ohne Ersatz abgeschlossen.')}>Ohne Ersatz schließen</IonButton></> : <IonButton size="small" fill="clear" color="danger" onClick={() => void mutate(`absence-cases/${item.id}/cancel/`, {}, 'Ausfall wurde storniert.')}>Meldung stornieren</IonButton>}
        </div>}
      </article>)}
      {!cases.length && <div className="absence-empty">Keine Ausfälle vorhanden.</div>}
    </div>

    <IonModal isOpen={reportOpen} onDidDismiss={() => setReportOpen(false)} className="absence-modal">
      <div className="absence-modal-body"><div className="absence-modal-head"><div><small>AUSFALL MELDEN</small><h2>{manager ? 'Ausfall / No-show erfassen' : 'Ich kann nicht arbeiten'}</h2></div><IonButton fill="clear" onClick={() => setReportOpen(false)}>Schließen</IonButton></div>
        <div className="absence-form"><IonSelect fill="outline" label="Schicht & Mitarbeiter" labelPlacement="floating" value={report.option} onIonChange={(e) => setReport({ ...report, option: val(e) })}>{reportOptions.map((option) => <IonSelectOption key={option.key} value={option.key}>{option.label}</IonSelectOption>)}</IonSelect><IonSelect fill="outline" label="Grund" labelPlacement="floating" value={report.kind} onIonChange={(e) => setReport({ ...report, kind: val(e) })}><IonSelectOption value="sick">Krank</IonSelectOption><IonSelectOption value="emergency">Notfall</IonSelectOption><IonSelectOption value="personal">Persönlich verhindert</IonSelectOption>{manager && <IonSelectOption value="no_show">Nicht erschienen</IonSelectOption>}<IonSelectOption value="other">Sonstiger Ausfall</IonSelectOption></IonSelect><IonTextarea className="full" fill="outline" label="Hinweis" labelPlacement="floating" value={report.note} onIonInput={(e) => setReport({ ...report, note: val(e) })}/></div>
        <div className="absence-modal-actions"><IonButton fill="outline" onClick={() => setReportOpen(false)}>Abbrechen</IonButton><IonButton disabled={busy || !report.option} onClick={() => void submitReport()}>{busy ? <IonSpinner name="dots"/> : 'Ausfall melden'}</IonButton></div>
      </div>
    </IonModal>

    <IonModal isOpen={!!candidateCase} onDidDismiss={() => setCandidateCase(undefined)} className="absence-modal candidate-modal">
      <div className="absence-modal-body"><div className="absence-modal-head"><div><small>FIND REPLACEMENT</small><h2>Geeignete Ersatzkräfte</h2><p>{candidateCase && `${candidateCase.shift_title} · ${dateTime(candidateCase.shift_starts_at)}`}</p></div><IonButton fill="clear" onClick={() => setCandidateCase(undefined)}>Schließen</IonButton></div>
        {!candidates.length ? <div className="absence-loading"><IonSpinner/><span>Eligibility wird geprüft …</span></div> : <div className="candidate-list">{candidates.map((candidate) => <article key={candidate.worker} className={candidate.eligible ? 'eligible' : 'blocked'}><IonCheckbox disabled={!candidate.eligible} checked={selectedCandidates.has(candidate.worker)} onIonChange={(e) => setSelectedCandidates((current) => { const next = new Set(current); e.detail.checked ? next.add(candidate.worker) : next.delete(candidate.worker); return next; })}/><div><b>{candidate.worker_name}</b><small>{candidate.eligible ? `Geeignet · Score ${candidate.score}` : candidate.blockers?.[0]?.message || 'Nicht geeignet'}</small>{candidate.warnings?.map((warning: any) => <em key={warning.code}>{warning.message}</em>)}</div>{candidate.eligible && <IonButton size="small" fill="outline" onClick={() => void direct(candidate)}>Direkt einsetzen</IonButton>}</article>)}</div>}
        <div className="candidate-footer"><IonInput fill="outline" type="number" min="1" max="72" label="Antwortfrist (Std.)" labelPlacement="floating" value={offerHours} onIonInput={(e) => setOfferHours(Number(val(e) || 12))}/><IonButton disabled={busy || !selectedCandidates.size} onClick={() => void sendOffers()}>An {selectedCandidates.size} Mitarbeiter senden</IonButton></div>
      </div>
    </IonModal>
    <IonToast isOpen={!!toast} message={toast} duration={4500} onDidDismiss={() => setToast('')}/>
  </section>;
}

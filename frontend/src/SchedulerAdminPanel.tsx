import React, { useEffect, useMemo, useState } from 'react';
import {
  IonBadge,
  IonButton,
  IonInput,
  IonLabel,
  IonModal,
  IonSegment,
  IonSegmentButton,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonToast,
  IonToggle,
} from '@ionic/react';
import { api } from './api';

const unpack = (data: any): any[] => (Array.isArray(data) ? data : data?.results || []);
const val = (event: any) => event.detail.value ?? '';
const modes = [
  ['off', 'Aus'],
  ['warn', 'Warnen'],
  ['block', 'Blockieren'],
];

export default function SchedulerAdminPanel({
  open,
  onClose,
  workers,
  clients,
  locations,
  positions,
}: {
  open: boolean;
  onClose: () => void;
  workers: any[];
  clients: any[];
  locations: any[];
  positions: any[];
}) {
  const [tab, setTab] = useState('rules');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [policies, setPolicies] = useState<any[]>([]);
  const [schedules, setSchedules] = useState<any[]>([]);
  const [memberships, setMemberships] = useState<any[]>([]);
  const [qualifications, setQualifications] = useState<any[]>([]);
  const [tags, setTags] = useState<any[]>([]);
  const [workerTags, setWorkerTags] = useState<any[]>([]);
  const [positionTags, setPositionTags] = useState<any[]>([]);
  const [templates, setTemplates] = useState<any[]>([]);
  const [readiness, setReadiness] = useState<any>();
  const [policy, setPolicy] = useState<any>();
  const [qualification, setQualification] = useState<any>({ level: 'qualified' });
  const [tagForm, setTagForm] = useState<any>({ color: '#155eef' });
  const [workerTagForm, setWorkerTagForm] = useState<any>({ verified: true });
  const [positionTagForm, setPositionTagForm] = useState<any>({ required: true });
  const [scheduleForm, setScheduleForm] = useState<any>({ timezone: 'Europe/Berlin', locations: [] });
  const [membershipForm, setMembershipForm] = useState<any>({ active: true });
  const [templateForm, setTemplateForm] = useState<any>({});

  async function load() {
    if (!open) return;
    const [p, s, m, q, t, wt, pt, st, ready] = await Promise.all([
      api('scheduling-policies/'),
      api('schedule-groups/'),
      api('schedule-memberships/'),
      api('position-qualifications/'),
      api('skill-tags/'),
      api('worker-skill-tags/'),
      api('position-skill-tags/'),
      api('schedule-templates/'),
      api('scheduling/readiness/'),
    ]);
    const pRows = unpack(p);
    setPolicies(pRows);
    setPolicy(pRows[0] || undefined);
    setSchedules(unpack(s));
    setMemberships(unpack(m));
    setQualifications(unpack(q));
    setTags(unpack(t));
    setWorkerTags(unpack(wt));
    setPositionTags(unpack(pt));
    setTemplates(unpack(st));
    setReadiness(ready);
  }

  useEffect(() => {
    void load();
  }, [open]);

  async function post(path: string, body: any, message: string) {
    setBusy(true);
    try {
      await api(path, { method: 'POST', body: JSON.stringify(body) });
      setToast(message);
      await load();
      return true;
    } catch (error: any) {
      setToast(error.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function remove(path: string, id: string) {
    setBusy(true);
    try {
      await api(`${path}/${id}/`, { method: 'DELETE' });
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function savePolicy() {
    if (!policy) return;
    setBusy(true);
    try {
      await api(`scheduling-policies/${policy.id}/`, { method: 'PATCH', body: JSON.stringify(policy) });
      setToast('Planungsregeln gespeichert.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  const activeWorkers = useMemo(() => workers.filter((worker) => worker.active !== false), [workers]);
  const activePositions = useMemo(() => positions.filter((position) => position.active !== false), [positions]);

  return (
    <IonModal isOpen={open} onDidDismiss={onClose} className="scheduler-admin-modal">
      <div className="scheduler-admin">
        <header className="scheduler-admin-head">
          <div>
            <small>WIW PARITY · PLANUNGSLOGIK</small>
            <h2>Scheduler konfigurieren</h2>
            <p>Qualifikationen, Regeln, Tags, Dienstpläne und Vorlagen zentral verwalten.</p>
          </div>
          <IonButton fill="clear" onClick={onClose}>Schließen</IonButton>
        </header>

        <IonSegment scrollable value={tab} onIonChange={(event) => setTab(String(val(event)))}>
          <IonSegmentButton value="rules"><IonLabel>Regeln</IonLabel></IonSegmentButton>
          <IonSegmentButton value="qualifications"><IonLabel>Positionen</IonLabel></IonSegmentButton>
          <IonSegmentButton value="tags"><IonLabel>Tags</IonLabel></IonSegmentButton>
          <IonSegmentButton value="schedules"><IonLabel>Dienstpläne</IonLabel></IonSegmentButton>
          <IonSegmentButton value="templates"><IonLabel>Vorlagen</IonLabel></IonSegmentButton>
          <IonSegmentButton value="readiness"><IonLabel>Readiness</IonLabel></IonSegmentButton>
        </IonSegment>

        <div className="scheduler-admin-body">
          {tab === 'rules' && (
            <section className="scheduler-admin-card">
              <div className="scheduler-card-head"><div><h3>Scheduling Rules</h3><p>Warnen oder hart blockieren – dieselben Regeln gelten für Claim, Assign, Swap und Auto-Assign.</p></div></div>
              {!policy ? <IonSpinner /> : (
                <div className="scheduler-form-grid">
                  <IonInput fill="outline" label="Regelwerk" labelPlacement="floating" value={policy.name} onIonInput={(e) => setPolicy({ ...policy, name: val(e) })} />
                  <IonInput fill="outline" type="number" label="Mindestruhezeit (Std.)" labelPlacement="floating" value={policy.min_rest_hours} onIonInput={(e) => setPolicy({ ...policy, min_rest_hours: val(e) })} />
                  <IonInput fill="outline" type="number" label="Max. Tage / Woche" labelPlacement="floating" value={policy.max_days_per_week} onIonInput={(e) => setPolicy({ ...policy, max_days_per_week: val(e) })} />
                  <IonInput fill="outline" type="number" label="Max. Tage am Stück" labelPlacement="floating" value={policy.max_consecutive_days} onIonInput={(e) => setPolicy({ ...policy, max_consecutive_days: val(e) })} />
                  <IonInput fill="outline" type="number" label="Max. Wochenstunden" labelPlacement="floating" value={policy.max_weekly_hours} onIonInput={(e) => setPolicy({ ...policy, max_weekly_hours: val(e) })} />
                  {[
                    ['qualification_mode', 'Positionsqualifikation'],
                    ['schedule_membership_mode', 'Dienstplan-Zuordnung'],
                    ['skill_tag_mode', 'Erforderliche Tags'],
                    ['availability_mode', 'Nicht verfügbar'],
                    ['time_off_mode', 'Genehmigte Abwesenheit'],
                    ['rest_mode', 'Ruhezeit'],
                    ['hours_mode', 'Wochenstunden'],
                    ['days_mode', 'Arbeitstage'],
                  ].map(([field, label]) => (
                    <IonSelect key={field} fill="outline" label={label} labelPlacement="floating" value={policy[field]} onIonChange={(e) => setPolicy({ ...policy, [field]: val(e) })}>
                      {modes.map(([mode, text]) => <IonSelectOption key={mode} value={mode}>{text}</IonSelectOption>)}
                    </IonSelect>
                  ))}
                  <div className="scheduler-full scheduler-actions"><IonButton disabled={busy} onClick={savePolicy}>Regeln speichern</IonButton></div>
                </div>
              )}
            </section>
          )}

          {tab === 'qualifications' && (
            <section className="scheduler-admin-card">
              <h3>Mitarbeiter ↔ Positionen</h3>
              <p>Nur qualifizierte Mitarbeiter können bei hartem Regelwerk eingeplant werden.</p>
              <div className="scheduler-form-grid">
                <IonSelect fill="outline" label="Mitarbeiter" labelPlacement="floating" value={qualification.worker} onIonChange={(e) => setQualification({ ...qualification, worker: val(e) })}>
                  {activeWorkers.map((worker) => <IonSelectOption key={worker.id} value={worker.id}>{worker.user_detail?.name || worker.user_detail?.email}</IonSelectOption>)}
                </IonSelect>
                <IonSelect fill="outline" label="Position" labelPlacement="floating" value={qualification.position} onIonChange={(e) => setQualification({ ...qualification, position: val(e) })}>
                  {activePositions.map((position) => <IonSelectOption key={position.id} value={position.id}>{position.name}</IonSelectOption>)}
                </IonSelect>
                <IonSelect fill="outline" label="Stufe" labelPlacement="floating" value={qualification.level} onIonChange={(e) => setQualification({ ...qualification, level: val(e) })}>
                  <IonSelectOption value="trainee">In Einarbeitung</IonSelectOption>
                  <IonSelectOption value="qualified">Qualifiziert</IonSelectOption>
                  <IonSelectOption value="lead">Leitung</IonSelectOption>
                </IonSelect>
                <IonInput fill="outline" type="date" label="Gültig bis" labelPlacement="floating" value={qualification.expires_on} onIonInput={(e) => setQualification({ ...qualification, expires_on: val(e) || null })} />
                <IonButton disabled={busy || !qualification.worker || !qualification.position} onClick={async () => {
                  if (await post('position-qualifications/', qualification, 'Qualifikation gespeichert.')) setQualification({ level: 'qualified' });
                }}>Qualifikation hinzufügen</IonButton>
              </div>
              <div className="scheduler-list">
                {qualifications.map((item) => <div key={item.id}><span><b>{item.worker_name || item.worker}</b><small>{item.position_name || item.position} · {item.level}</small></span><IonButton size="small" fill="clear" color="danger" onClick={() => void remove('position-qualifications', item.id)}>Entfernen</IonButton></div>)}
              </div>
            </section>
          )}

          {tab === 'tags' && (
            <section className="scheduler-admin-card">
              <h3>Skills, Zertifikate & Tags</h3>
              <div className="scheduler-form-grid">
                <IonInput fill="outline" label="Neuer Tag" labelPlacement="floating" value={tagForm.name} onIonInput={(e) => setTagForm({ ...tagForm, name: val(e) })} />
                <IonInput fill="outline" {...({ type: 'color' } as any)} label="Farbe" labelPlacement="floating" value={tagForm.color} onIonInput={(e) => setTagForm({ ...tagForm, color: val(e) })} />
                <IonButton disabled={!tagForm.name || busy} onClick={async () => { if (await post('skill-tags/', tagForm, 'Tag angelegt.')) setTagForm({ color: '#155eef' }); }}>Tag anlegen</IonButton>
              </div>
              <div className="scheduler-tag-strip">{tags.map((tag) => <IonBadge key={tag.id}>{tag.name}</IonBadge>)}</div>
              <hr />
              <div className="scheduler-form-grid">
                <IonSelect fill="outline" label="Mitarbeiter" labelPlacement="floating" value={workerTagForm.worker} onIonChange={(e) => setWorkerTagForm({ ...workerTagForm, worker: val(e) })}>{activeWorkers.map((worker) => <IonSelectOption key={worker.id} value={worker.id}>{worker.user_detail?.name || worker.user_detail?.email}</IonSelectOption>)}</IonSelect>
                <IonSelect fill="outline" label="Tag / Zertifikat" labelPlacement="floating" value={workerTagForm.tag} onIonChange={(e) => setWorkerTagForm({ ...workerTagForm, tag: val(e) })}>{tags.map((tag) => <IonSelectOption key={tag.id} value={tag.id}>{tag.name}</IonSelectOption>)}</IonSelect>
                <IonInput fill="outline" type="date" label="Gültig bis" labelPlacement="floating" value={workerTagForm.expires_on} onIonInput={(e) => setWorkerTagForm({ ...workerTagForm, expires_on: val(e) || null })} />
                <label className="scheduler-toggle">Verifiziert <IonToggle checked={workerTagForm.verified !== false} onIonChange={(e) => setWorkerTagForm({ ...workerTagForm, verified: e.detail.checked })} /></label>
                <IonButton disabled={busy || !workerTagForm.worker || !workerTagForm.tag} onClick={async () => { if (await post('worker-skill-tags/', workerTagForm, 'Mitarbeiter-Tag gespeichert.')) setWorkerTagForm({ verified: true }); }}>Mitarbeiter zuordnen</IonButton>
              </div>
              <div className="scheduler-list">{workerTags.map((item) => <div key={item.id}><span><b>{item.worker_name}</b><small>{item.tag_name}{item.expires_on ? ` · bis ${item.expires_on}` : ''}</small></span><IonButton size="small" fill="clear" color="danger" onClick={() => void remove('worker-skill-tags', item.id)}>Entfernen</IonButton></div>)}</div>
              <hr />
              <div className="scheduler-form-grid">
                <IonSelect fill="outline" label="Position" labelPlacement="floating" value={positionTagForm.position} onIonChange={(e) => setPositionTagForm({ ...positionTagForm, position: val(e) })}>{activePositions.map((position) => <IonSelectOption key={position.id} value={position.id}>{position.name}</IonSelectOption>)}</IonSelect>
                <IonSelect fill="outline" label="Erforderlicher Tag" labelPlacement="floating" value={positionTagForm.tag} onIonChange={(e) => setPositionTagForm({ ...positionTagForm, tag: val(e) })}>{tags.map((tag) => <IonSelectOption key={tag.id} value={tag.id}>{tag.name}</IonSelectOption>)}</IonSelect>
                <IonButton disabled={busy || !positionTagForm.position || !positionTagForm.tag} onClick={async () => { if (await post('position-skill-tags/', positionTagForm, 'Pflicht-Tag gespeichert.')) setPositionTagForm({ required: true }); }}>Als Pflicht setzen</IonButton>
              </div>
              <div className="scheduler-list">{positionTags.map((item) => <div key={item.id}><span><b>{item.position_name}</b><small>{item.tag_name}</small></span><IonButton size="small" fill="clear" color="danger" onClick={() => void remove('position-skill-tags', item.id)}>Entfernen</IonButton></div>)}</div>
            </section>
          )}

          {tab === 'schedules' && (
            <section className="scheduler-admin-card">
              <h3>Dienstpläne & Memberships</h3>
              <div className="scheduler-form-grid">
                <IonInput fill="outline" label="Dienstplanname" labelPlacement="floating" value={scheduleForm.name} onIonInput={(e) => setScheduleForm({ ...scheduleForm, name: val(e) })} />
                <IonInput fill="outline" label="Zeitzone" labelPlacement="floating" value={scheduleForm.timezone} onIonInput={(e) => setScheduleForm({ ...scheduleForm, timezone: val(e) })} />
                <IonSelect multiple fill="outline" label="Einsatzorte" labelPlacement="floating" value={scheduleForm.locations || []} onIonChange={(e) => setScheduleForm({ ...scheduleForm, locations: val(e) })}>{locations.map((location) => <IonSelectOption key={location.id} value={location.id}>{location.name}</IonSelectOption>)}</IonSelect>
                <IonButton disabled={busy || !scheduleForm.name} onClick={async () => { if (await post('schedule-groups/', scheduleForm, 'Dienstplan angelegt.')) setScheduleForm({ timezone: 'Europe/Berlin', locations: [] }); }}>Dienstplan anlegen</IonButton>
              </div>
              <div className="scheduler-list">{schedules.map((item) => <div key={item.id}><span><b>{item.name}</b><small>{item.location_names?.join(', ') || 'Keine Orte'}</small></span></div>)}</div>
              <hr />
              <div className="scheduler-form-grid">
                <IonSelect fill="outline" label="Dienstplan" labelPlacement="floating" value={membershipForm.schedule} onIonChange={(e) => setMembershipForm({ ...membershipForm, schedule: val(e) })}>{schedules.map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect>
                <IonSelect fill="outline" label="Mitarbeiter" labelPlacement="floating" value={membershipForm.worker} onIonChange={(e) => setMembershipForm({ ...membershipForm, worker: val(e) })}>{activeWorkers.map((worker) => <IonSelectOption key={worker.id} value={worker.id}>{worker.user_detail?.name || worker.user_detail?.email}</IonSelectOption>)}</IonSelect>
                <IonButton disabled={busy || !membershipForm.schedule || !membershipForm.worker} onClick={async () => { if (await post('schedule-memberships/', membershipForm, 'Dienstplan-Zuordnung gespeichert.')) setMembershipForm({ active: true }); }}>Zuordnen</IonButton>
              </div>
              <div className="scheduler-list">{memberships.map((item) => <div key={item.id}><span><b>{item.worker_name}</b><small>{item.schedule_name}</small></span><IonButton size="small" fill="clear" color="danger" onClick={() => void remove('schedule-memberships', item.id)}>Entfernen</IonButton></div>)}</div>
            </section>
          )}

          {tab === 'templates' && (
            <section className="scheduler-admin-card">
              <h3>Wochenvorlagen</h3>
              <p>Vorlagen können später direkt auf eine Zielwoche angewendet werden. Jede Vorlage kann beliebig viele Schichtbausteine enthalten.</p>
              <div className="scheduler-form-grid">
                <IonInput fill="outline" label="Vorlagenname" labelPlacement="floating" value={templateForm.name} onIonInput={(e) => setTemplateForm({ ...templateForm, name: val(e) })} />
                <IonSelect fill="outline" label="Dienstplan (optional)" labelPlacement="floating" value={templateForm.schedule} onIonChange={(e) => setTemplateForm({ ...templateForm, schedule: val(e) || null })}><IonSelectOption value="">Ohne feste Zuordnung</IonSelectOption>{schedules.map((item) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}</IonSelect>
                <IonTextarea fill="outline" label="Notiz" labelPlacement="floating" value={templateForm.notes} onIonInput={(e) => setTemplateForm({ ...templateForm, notes: val(e) })} />
                <IonButton disabled={busy || !templateForm.name} onClick={async () => { if (await post('schedule-templates/', { ...templateForm, items: [] }, 'Vorlage angelegt.')) setTemplateForm({}); }}>Vorlage anlegen</IonButton>
              </div>
              <div className="scheduler-list">{templates.map((item) => <div key={item.id}><span><b>{item.name}</b><small>{item.schedule_name || 'Global'} · {item.items?.length || 0} Bausteine</small></span></div>)}</div>
              <div className="scheduler-note">Schichtbausteine können über dieselbe API als <code>items</code> gepflegt werden; der nächste Scheduler-Schritt ergänzt dafür den visuellen Wocheneditor.</div>
            </section>
          )}

          {tab === 'readiness' && (
            <section className="scheduler-admin-card">
              <h3>WIW Replacement Readiness · Scheduler</h3>
              {!readiness ? <IonSpinner /> : (
                <>
                  <div className="scheduler-readiness-grid">
                    <div><small>Qualifikationsabdeckung</small><strong>{readiness.qualification_coverage_percent}%</strong></div>
                    <div><small>Aktive Regelwerke</small><strong>{readiness.policies}</strong></div>
                    <div><small>Dienstpläne</small><strong>{readiness.schedules}</strong></div>
                    <div><small>Vorlagen</small><strong>{readiness.templates}</strong></div>
                  </div>
                  <div className={`scheduler-readiness-state ${readiness.replacement_ready ? 'ready' : 'pending'}`}>
                    <b>{readiness.replacement_ready ? 'Scheduler ist hart abgesichert.' : 'Noch nicht bereit für harten WIW-Cutover.'}</b>
                    <p>Vor dem Cutover müssen alle aktiven Mitarbeiter Positionsqualifikationen besitzen und die kritischen Regeln auf „Blockieren“ stehen.</p>
                  </div>
                </>
              )}
            </section>
          )}
        </div>
        <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={() => setToast('')} />
      </div>
    </IonModal>
  );
}

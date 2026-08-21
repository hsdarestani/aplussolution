import React, { useEffect, useMemo, useState } from 'react';
import { IonBadge, IonButton, IonInput, IonSelect, IonSelectOption, IonTextarea, IonToggle } from '@ionic/react';
import { api, User } from './api';
import './premium-operations.css';

const unpack = (value: any): any[] => value?.results || value || [];
const isoDate = (date = new Date()) => date.toISOString().slice(0, 10);
const addDays = (days: number) => { const date = new Date(); date.setDate(date.getDate() + days); return isoDate(date); };

function SwitchControl({label,description,checked,onChange}:{label:string;description:string;checked:boolean;onChange:(value:boolean)=>void}) {
  return <div className="premium-switch-row">
    <div className="premium-switch-copy"><strong>{label}</strong><span>{description}</span></div>
    <IonToggle aria-label={label} checked={checked} onIonChange={event=>onChange(event.detail.checked)} />
  </div>;
}

function NumberControl({label,value,onChange,suffix}:{label:string;value:any;onChange:(value:any)=>void;suffix?:string}) {
  return <label className="premium-field-control"><span>{label}</span><div className="premium-input-shell"><IonInput aria-label={label} type="number" value={value} onIonInput={event=>onChange(event.detail.value)} />{suffix&&<em>{suffix}</em>}</div></label>;
}

function DateControl({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}) {
  return <label className="premium-field-control"><span>{label}</span><div className="premium-input-shell"><IonInput aria-label={label} type="date" value={value} onIonInput={event=>onChange(String(event.detail.value||''))}/></div></label>;
}

export default function PremiumOperations({ user }: { user: User }) {
  const manager = ['admin', 'manager'].includes(user.role);
  const admin = user.role === 'admin';
  const worker = user.role === 'worker';
  const [policy, setPolicy] = useState<any>();
  const [pickup, setPickup] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [taskLists, setTaskLists] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [reports, setReports] = useState<any[]>([]);
  const [apiKeys, setApiKeys] = useState<any[]>([]);
  const [webhooks, setWebhooks] = useState<any[]>([]);
  const [saml, setSaml] = useState<any>({ enabled: false });
  const [mine, setMine] = useState<any[]>([]);
  const [autoRange, setAutoRange] = useState({ start: isoDate(), end: addDays(14), location_id: '' });
  const [autoResult, setAutoResult] = useState<any>();
  const [newTask, setNewTask] = useState({ name: '', items: '', location_id: '' });
  const [calloutShift, setCalloutShift] = useState('');
  const [calloutReason, setCalloutReason] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [issuedKey, setIssuedKey] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [samlData, taskData] = await Promise.all([api('auth/saml/status/'), api('premium/task-runs/')]);
      setSaml(samlData); setTasks(unpack(taskData));
      if (worker) { const shifts = await api('shifts/mine/?ordering=starts_at'); setMine(unpack(shifts).filter((item: any) => new Date(item.ends_at) >= new Date())); }
      if (manager) {
        const [p, approvals, lists, locs, reportDefs] = await Promise.all([api('premium/scheduling-policy/'),api('premium/pickup-requests/'),api('premium/task-lists/'),api('locations/?ordering=name'),api('premium/reports/')]);
        setPolicy(p); setPickup(unpack(approvals)); setTaskLists(unpack(lists)); setLocations(unpack(locs)); setReports(unpack(reportDefs));
      }
      if (admin) { const [keys, hooks] = await Promise.all([api('premium/api-keys/'), api('premium/webhooks/')]); setApiKeys(unpack(keys)); setWebhooks(unpack(hooks)); }
    } catch (error: any) { setMessage(error.message || 'Workforce-Pro-Daten konnten nicht geladen werden.'); }
  };
  useEffect(() => { void load(); }, [user.role]);

  const run = async (fn: () => Promise<any>, success: string) => { setBusy(true); try { const result = await fn(); setMessage(success); await load(); return result; } catch (error: any) { setMessage(error.message || 'Aktion fehlgeschlagen.'); } finally { setBusy(false); } };
  const savePolicy = () => run(() => api('premium/scheduling-policy/', { method: 'PATCH', body: JSON.stringify(policy) }), 'Planungsregeln gespeichert.');
  const autoSchedule = async (apply: boolean) => { const result = await run(() => api('premium/auto-schedule/', {method:'POST',body:JSON.stringify({...autoRange,apply})}), apply?'Automatische Planung angewendet.':'Planungsvorschlag berechnet.'); if(result)setAutoResult(result); };
  const decidePickup = (id: string, status: 'approved' | 'rejected') => run(() => api(`premium/pickup-requests/${id}/decide/`, { method: 'POST', body: JSON.stringify({ status }) }),status==='approved'?'Schichtübernahme genehmigt.':'Schichtübernahme abgelehnt.');
  const createTaskList = () => { const items=newTask.items.split('\n').map(title=>title.trim()).filter(Boolean).map(title=>({title,required:true})); if(!newTask.name||!items.length)return setMessage('Name und mindestens eine Aufgabe eingeben.'); return run(()=>api('premium/task-lists/',{method:'POST',body:JSON.stringify({name:newTask.name,kind:'shift',location_id:newTask.location_id||null,items})}),'Aufgabenliste erstellt.'); };
  const completeTask = (runId:string,itemId:string)=>run(()=>api(`premium/task-runs/${runId}/complete/`,{method:'POST',body:JSON.stringify({item_id:itemId})}),'Aufgabe erledigt.');
  const callout = () => { if(!calloutShift)return setMessage('Bitte eine Schicht auswählen.'); return run(()=>api('premium/callouts/',{method:'POST',body:JSON.stringify({shift_id:calloutShift,reason:calloutReason})}),'Ausfall gemeldet; die Kapazität ist wieder offen.'); };
  const createStandardReports = async () => { const desired=[['Schichtbericht','shifts'],['Zeiterfassung','times'],['Schichtverlauf','shift_history'],['Abwesenheiten','time_off'],['Personalkosten & Forecast','labor']]; setBusy(true); try { for(const [name,kind] of desired){if(!reports.some(item=>item.kind===kind))await api('premium/reports/',{method:'POST',body:JSON.stringify({name,kind,shared:true})});} setMessage('Standardberichte sind verfügbar.'); await load(); } catch(error:any){setMessage(error.message||'Berichte konnten nicht angelegt werden.');} finally{setBusy(false);} };
  const issueApiKey = async () => { const result=await run(()=>api('premium/api-keys/',{method:'POST',body:JSON.stringify({name:'Operations API',scopes:['users:read','shifts:read','shifts:write','times:read','time_off:read','time_off:write','tasks:read']})}),'API-Key erstellt. Jetzt sicher kopieren.'); if(result?.key)setIssuedKey(result.key); };
  const revokeApiKey = (id:string) => run(()=>api(`premium/api-keys/${id}/`,{method:'DELETE'}),'API-Schlüssel widerrufen.');
  const createWebhook = () => { if(!webhookUrl)return setMessage('Webhook-URL eingeben.'); return run(()=>api('premium/webhooks/',{method:'POST',body:JSON.stringify({name:'Operations Webhook',endpoint_url:webhookUrl,events:['shifts.*','times.*','time_off.*','callouts.*','tasks.*']})}),'Webhook erstellt.'); };
  const testWebhook = (id:string) => run(()=>api(`premium/webhooks/${id}/test/`,{method:'POST'}),'Webhook-Test ausgelöst.');
  const deleteWebhook = (id:string) => run(()=>api(`premium/webhooks/${id}/`,{method:'DELETE'}),'Webhook gelöscht.');
  const pendingRequiredTasks = useMemo(()=>tasks.reduce((sum,taskRun)=>sum+(taskRun.items||[]).filter((item:any)=>item.required&&!item.completed).length,0),[tasks]);
  if(!manager&&!worker)return null;

  return <section className="operations-panel premium-ops" data-testid="premium-operations-panel">
    <div className="premium-head"><div><small>A+ WORKFORCE PRO</small><h3>{worker?'Meine erweiterten Funktionen':'Erweiterte Workforce-Steuerung'}</h3><p>{worker?'Aufgaben und kurzfristige Ausfälle direkt in der App bearbeiten.':'Automatische Dienstplanung, Regeln, Forecast, Aufgaben, Berichte, API, Webhooks und Enterprise-SSO.'}</p></div><div className="premium-badges">{manager&&<IonBadge color="success">Nativ</IonBadge>}{admin&&<IonBadge color={saml.enabled?'success':'medium'}>SAML {saml.enabled?'aktiv':'bereit'}</IonBadge>}{worker&&<IonBadge color={pendingRequiredTasks?'warning':'success'}>{pendingRequiredTasks} Aufgaben offen</IonBadge>}</div></div>
    {message&&<div className="premium-message">{message}</div>}

    {manager&&policy&&<details open className="premium-box premium-policy-box"><summary>Planungsregeln & automatische Dienstplanung</summary>
      <div className="premium-toggle-grid">
        <SwitchControl label="Automatische Dienstplanung" description="Offene Schichten anhand Regeln und Verfügbarkeit automatisch vorschlagen." checked={!!policy.auto_schedule_enabled} onChange={checked=>setPolicy({...policy,auto_schedule_enabled:checked})}/>
        <SwitchControl label="OpenShift-Übernahme freigeben" description="Übernahmen durch Mitarbeiter benötigen eine Freigabe." checked={!!policy.pickup_approval_required} onChange={checked=>setPolicy({...policy,pickup_approval_required:checked})}/>
        <SwitchControl label="Standortübergreifender Personaleinsatz" description="Geeignete Mitarbeiter zwischen Einsatzorten berücksichtigen." checked={!!policy.labor_sharing_enabled} onChange={checked=>setPolicy({...policy,labor_sharing_enabled:checked})}/>
        <SwitchControl label="Überlappende OpenShifts zulassen" description="Offene Bedarfe dürfen sich zeitlich überschneiden." checked={!!policy.allow_overlapping_open_shifts} onChange={checked=>setPolicy({...policy,allow_overlapping_open_shifts:checked})}/>
        <SwitchControl label="Mehrere Schichten pro Tag" description="Mehr als einen Einsatz pro Mitarbeiter und Kalendertag erlauben." checked={!!policy.allow_multiple_shifts_per_day} onChange={checked=>setPolicy({...policy,allow_multiple_shifts_per_day:checked})}/>
        <SwitchControl label="Zeitzonenumschaltung" description="Alternative Zeitzonen in der Planung verfügbar machen." checked={!!policy.timezone_toggle_enabled} onChange={checked=>setPolicy({...policy,timezone_toggle_enabled:checked})}/>
      </div>
      <div className="premium-rule-grid">
        <NumberControl label="Ruhezeit zwischen Tagen" suffix="Std." value={policy.min_hours_between_days} onChange={value=>setPolicy({...policy,min_hours_between_days:value})}/>
        <NumberControl label="Maximale Stunden pro Tag" suffix="Std." value={policy.max_hours_per_day} onChange={value=>setPolicy({...policy,max_hours_per_day:value})}/>
        <NumberControl label="Maximale Stunden pro Woche" suffix="Std." value={policy.max_hours_per_week} onChange={value=>setPolicy({...policy,max_hours_per_week:value})}/>
        <NumberControl label="Maximale Tage in Folge" value={policy.max_days_in_row} onChange={value=>setPolicy({...policy,max_days_in_row:value})}/>
      </div>
      <div className="premium-actions"><IonButton disabled={busy} onClick={savePolicy}>Regeln speichern</IonButton></div>
      <div className="premium-subsection"><div><b>Automatisch planen</b><span>Zeitraum und optional einen Einsatzort wählen. Zuerst kann eine Vorschau berechnet werden.</span></div>
        <div className="premium-auto-grid"><DateControl label="Von" value={autoRange.start} onChange={start=>setAutoRange({...autoRange,start})}/><DateControl label="Bis" value={autoRange.end} onChange={end=>setAutoRange({...autoRange,end})}/><label className="premium-field-control"><span>Einsatzort</span><div className="premium-input-shell select"><IonSelect aria-label="Einsatzort" value={autoRange.location_id} onIonChange={event=>setAutoRange({...autoRange,location_id:event.detail.value})}><IonSelectOption value="">Alle Einsatzorte</IonSelectOption>{locations.map(location=><IonSelectOption key={location.id} value={location.id}>{location.name}</IonSelectOption>)}</IonSelect></div></label></div>
        <div className="premium-actions"><IonButton fill="outline" disabled={busy} onClick={()=>autoSchedule(false)}>Vorschau</IonButton><IonButton disabled={busy} onClick={()=>autoSchedule(true)}>Automatisch besetzen</IonButton></div>
        {autoResult&&<div className="premium-result"><b>{autoResult.assigned}</b> besetzt · <b>{autoResult.unfilled}</b> offen</div>}
      </div>
    </details>}

    {manager&&pickup.length>0&&<details open className="premium-box"><summary>Offene Übernahmeanfragen <IonBadge color="warning">{pickup.length}</IonBadge></summary>{pickup.map(item=><div className="premium-row" key={item.id}><div><b>{item.worker}</b><span>{new Date(item.starts_at).toLocaleString('de-DE')} · {item.location} · {item.position}</span></div><div><IonButton size="small" color="success" onClick={()=>decidePickup(item.id,'approved')}>Genehmigen</IonButton><IonButton size="small" fill="outline" color="danger" onClick={()=>decidePickup(item.id,'rejected')}>Ablehnen</IonButton></div></div>)}</details>}

    {manager&&<details className="premium-box"><summary>Aufgabenlisten & individuelle Berichte</summary><div className="premium-fields"><IonInput fill="outline" label="Name der Aufgabenliste" labelPlacement="floating" value={newTask.name} onIonInput={event=>setNewTask({...newTask,name:String(event.detail.value||'')})}/><IonSelect fill="outline" label="Einsatzort optional" labelPlacement="floating" value={newTask.location_id} onIonChange={event=>setNewTask({...newTask,location_id:event.detail.value})}><IonSelectOption value="">Alle</IonSelectOption>{locations.map(location=><IonSelectOption key={location.id} value={location.id}>{location.name}</IonSelectOption>)}</IonSelect><IonTextarea className="premium-wide" fill="outline" autoGrow label="Eine Aufgabe pro Zeile" labelPlacement="floating" value={newTask.items} onIonInput={event=>setNewTask({...newTask,items:String(event.detail.value||'')})}/></div><div className="premium-actions"><IonButton fill="outline" onClick={createTaskList}>Aufgabenliste erstellen</IonButton><IonButton fill="outline" onClick={createStandardReports}>Standardberichte anlegen</IonButton></div><div className="premium-result">{taskLists.length} Aufgabenlisten · {reports.length} gespeicherte Berichte</div></details>}

    {worker&&<><details open className="premium-box"><summary>Meine Schichtaufgaben</summary>{!tasks.length&&<p className="premium-muted">Keine Aufgaben zugewiesen.</p>}{tasks.map(taskRun=><div className="premium-task-run" key={taskRun.id}><b>{taskRun.name}</b><small>{taskRun.location} · {new Date(taskRun.run_date).toLocaleDateString('de-DE')}</small>{(taskRun.items||[]).map((item:any)=><button key={item.id} className={`premium-task ${item.completed?'done':''}`} disabled={item.completed||busy} onClick={()=>completeTask(taskRun.id,item.id)}><span>{item.completed?'✓':'○'}</span>{item.title}{item.required&&!item.completed?' *':''}</button>)}</div>)}</details><details className="premium-box"><summary>Ausfall innerhalb 24 Stunden melden</summary><IonSelect fill="outline" label="Meine Schicht" labelPlacement="floating" value={calloutShift} onIonChange={event=>setCalloutShift(event.detail.value)}>{mine.map(shift=><IonSelectOption key={shift.id} value={shift.id}>{new Date(shift.starts_at).toLocaleString('de-DE')} · {shift.location_name||shift.location?.name||shift.position_name}</IonSelectOption>)}</IonSelect><IonTextarea fill="outline" label="Grund / Hinweis" labelPlacement="floating" value={calloutReason} onIonInput={event=>setCalloutReason(String(event.detail.value||''))}/><div className="premium-actions"><IonButton color="warning" disabled={busy} onClick={callout}>Ausfall melden</IonButton></div></details></>}

    {admin&&<details className="premium-box" data-testid="premium-enterprise-controls"><summary>API, Webhooks & Unternehmens-SSO</summary>
      <div className="premium-enterprise"><div><b>Öffentliche API</b><span>{apiKeys.filter(item=>item.active).length} aktive · {apiKeys.length} gespeichert</span><IonButton size="small" fill="outline" onClick={issueApiKey}>Neuen API-Schlüssel</IonButton></div><div><b>SAML 2.0 / SSO</b><span>{saml.enabled?'Identitätsanbieter ist konfiguriert':'Code aktiv, Zugangsdaten des Identitätsanbieters fehlen'}</span><IonBadge color={saml.enabled?'success':'medium'}>{saml.enabled?'Aktiv':'Konfigurieren'}</IonBadge></div></div>
      {issuedKey&&<div className="premium-key"><b>Nur jetzt sichtbar:</b><code>{issuedKey}</code></div>}
      {apiKeys.length>0&&<div className="premium-enterprise-list" data-testid="api-key-list">{apiKeys.map(key=><div className="premium-row" key={key.id}><div><b>{key.name}</b><span>Prefix {key.prefix} · {key.active?'aktiv':'widerrufen'}{key.last_used_at?` · zuletzt genutzt ${new Date(key.last_used_at).toLocaleString('de-DE')}`:''}</span></div>{key.active&&<IonButton size="small" color="danger" fill="outline" disabled={busy} onClick={()=>revokeApiKey(key.id)}>Widerrufen</IonButton>}</div>)}</div>}
      <div className="premium-fields"><IonInput className="premium-wide" fill="outline" type="url" label="Webhook-HTTPS-URL" labelPlacement="floating" value={webhookUrl} onIonInput={event=>setWebhookUrl(String(event.detail.value||''))}/></div><div className="premium-actions"><IonButton fill="outline" onClick={createWebhook}>Webhook anlegen</IonButton></div>
      {webhooks.length>0&&<div className="premium-enterprise-list" data-testid="webhook-list">{webhooks.map(hook=><div className="premium-row" key={hook.id}><div><b>{hook.name}</b><span>{hook.endpoint_url} · {hook.deliveries} Auslieferungen</span></div><div><IonButton size="small" fill="outline" disabled={busy} onClick={()=>testWebhook(hook.id)}>Testen</IonButton><IonButton size="small" color="danger" fill="outline" disabled={busy} onClick={()=>deleteWebhook(hook.id)}>Löschen</IonButton></div></div>)}</div>}
      <div className="premium-result">{webhooks.length} Webhook-Abos · signierte HMAC-Auslieferung mit Wiederholungsversuch</div>
    </details>}
  </section>;
}

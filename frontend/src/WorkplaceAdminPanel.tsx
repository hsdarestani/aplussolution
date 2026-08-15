import React, { useEffect, useMemo, useState } from 'react';
import {
  IonBadge,
  IonButton,
  IonCard,
  IonCardContent,
  IonInput,
  IonItem,
  IonLabel,
  IonModal,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonToggle,
} from '@ionic/react';
import { api, User } from './api';
import './workplace-admin.css';

type Option = { id: string; name: string; email?: string; employee_number?: string; role?: string };
type Role = {
  id: string; code: string; name: string; description: string; permissions: string[];
  wage_visibility: 'none'|'scoped'|'all'; is_system: boolean; active: boolean; assignment_count: number;
};
type Assignment = {
  id: string; user: string; user_name: string; access_role: string; role_name: string; role_code: string;
  scope_mode: 'all'|'scoped'; schedule_groups: string[]; schedule_names: string[]; locations: string[];
  location_names: string[]; workers: string[]; worker_names: string[]; can_share_labor: boolean; active: boolean;
  capabilities: string[];
};
type Settings = {
  company_name: string; timezone: string; week_starts_on: number; time_format: '24h'|'12h'; currency: string;
  overtime_daily_hours: string; overtime_weekly_hours: string; overtime_mode: 'off'|'warn'|'block';
  overtime_multiplier: string; labor_sharing_enabled: boolean; manager_can_manage_roles: boolean;
};
type Snapshot = {
  settings: Settings; roles: Role[]; assignments: Assignment[]; capability_catalog: string[];
  managers: Option[]; workers: Option[]; schedules: Option[]; locations: Option[];
  current_user: { capabilities: string[]; scope: any };
  can_manage_settings: boolean; can_manage_roles: boolean;
};

const WEEKDAYS = ['Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag','Sonntag'];
const CAP_LABELS: Record<string,string> = {
  'manager.access':'Manager-Zugang', 'workplace.view':'Betrieb ansehen', 'workplace.manage':'Betrieb konfigurieren',
  'roles.view':'Rollen ansehen', 'roles.manage':'Rollen verwalten', 'people.view':'Personal ansehen', 'people.edit':'Personal bearbeiten',
  'clients.view':'Kunden ansehen', 'clients.edit':'Kunden bearbeiten', 'schedule.view':'Dienstplan ansehen', 'schedule.edit':'Dienstplan bearbeiten',
  'schedule.publish':'Dienstplan veröffentlichen', 'attendance.view':'Zeiten ansehen', 'attendance.edit':'Zeiten bearbeiten',
  'payroll.view':'Abrechnung ansehen', 'payroll.review':'Abrechnung prüfen', 'payroll.export':'Abrechnung exportieren',
  'wage.view':'Löhne sehen', 'labor.share':'Mitarbeiter bereichsübergreifend teilen', 'reports.view':'Berichte ansehen',
  'documents.manage':'Dokumente verwalten',
};
const WAGE_LABEL: Record<string,string> = {none:'Keine Lohndaten', scoped:'Nur eigener Bereich', all:'Alle Lohndaten'};
const emptyAssignment = {user:'',access_role:'',scope_mode:'scoped',schedule_groups:[] as string[],locations:[] as string[],workers:[] as string[],can_share_labor:false,active:true};
const emptyRole = {code:'',name:'',description:'',permissions:[] as string[],wage_visibility:'none',active:true};
const val = (e:any) => e.detail.value ?? '';

export default function WorkplaceAdminPanel({ user }: { user: User }) {
  const initialCaps = user.capabilities || [];
  const eligible = user.role === 'admin' || initialCaps.includes('workplace.view') || initialCaps.includes('roles.view');
  const [data,setData] = useState<Snapshot|null>(null);
  const [settings,setSettings] = useState<Settings|null>(null);
  const [loading,setLoading] = useState(false);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [assignmentOpen,setAssignmentOpen] = useState(false);
  const [assignmentId,setAssignmentId] = useState<string|null>(null);
  const [assignment,setAssignment] = useState({...emptyAssignment});
  const [roleOpen,setRoleOpen] = useState(false);
  const [roleId,setRoleId] = useState<string|null>(null);
  const [role,setRole] = useState({...emptyRole});

  async function load() {
    if (!eligible) return;
    setLoading(true); setError('');
    try {
      const result = await api<Snapshot>('workplace/snapshot/');
      setData(result); setSettings(result.settings);
    } catch (e:any) { setError(e.message); }
    finally { setLoading(false); }
  }
  useEffect(()=>{ void load(); },[eligible]);
  const caps = data?.current_user?.capabilities || initialCaps;
  const canSettings = user.role === 'admin' || !!data?.can_manage_settings;
  const canRoles = user.role === 'admin' || !!data?.can_manage_roles;
  const scopeLabel = useMemo(()=>{
    const scope=data?.current_user?.scope;
    if (!scope) return '–';
    return scope.mode === 'all' ? 'Gesamter Betrieb' : scope.mode === 'self' ? 'Nur eigenes Profil' : 'Zugeordneter Bereich';
  },[data]);
  if (!eligible) return null;

  async function saveSettings() {
    if (!settings || !canSettings) return;
    setBusy(true);setError('');
    try {
      await api('workplace/settings/',{method:'PATCH',body:JSON.stringify(settings)});
      setNotice('Betriebseinstellungen gespeichert.'); await load();
    } catch(e:any){setError(e.message);} finally{setBusy(false);}
  }
  function editAssignment(item?:Assignment) {
    setAssignmentId(item?.id || null);
    setAssignment(item ? {user:item.user,access_role:item.access_role,scope_mode:item.scope_mode,schedule_groups:item.schedule_groups||[],locations:item.locations||[],workers:item.workers||[],can_share_labor:item.can_share_labor,active:item.active} : {...emptyAssignment});
    setAssignmentOpen(true);
  }
  async function saveAssignment() {
    if (!canRoles || !assignment.user || !assignment.access_role) return;
    setBusy(true);setError('');
    try {
      await api(assignmentId ? `access-assignments/${assignmentId}/` : 'access-assignments/',{method:assignmentId?'PATCH':'POST',body:JSON.stringify(assignment)});
      setAssignmentOpen(false); setNotice('Rollen-Zuweisung gespeichert.'); await load();
    }catch(e:any){setError(e.message);}finally{setBusy(false);}
  }
  function editRole(item?:Role) {
    setRoleId(item?.id || null);
    setRole(item ? {code:item.code,name:item.name,description:item.description||'',permissions:item.permissions||[],wage_visibility:item.wage_visibility,active:item.active} : {...emptyRole});
    setRoleOpen(true);
  }
  async function saveRole() {
    if (!canRoles || !role.name || !role.code) return;
    setBusy(true);setError('');
    try {
      await api(roleId ? `access-roles/${roleId}/` : 'access-roles/',{method:roleId?'PATCH':'POST',body:JSON.stringify(role)});
      setRoleOpen(false); setNotice('Rolle gespeichert.'); await load();
    }catch(e:any){setError(e.message);}finally{setBusy(false);}
  }

  return <section className="workplace-admin" data-testid="workplace-admin-panel">
    <div className="workplace-title">
      <div><small>A+ WORKFORCE · PREMIUM ADMIN</small><h2>Betrieb, Rollen & Berechtigungen</h2><p>Granulare Zugriffe, Verantwortungsbereiche, Lohndaten und Arbeitszeitregeln zentral steuern.</p></div>
      <div className="workplace-title-badges"><IonBadge color="primary">{scopeLabel}</IonBadge>{data?.current_user?.scope?.role && <IonBadge color="medium">{data.current_user.scope.role}</IonBadge>}</div>
    </div>
    {error && <div className="workplace-error">{error}</div>}
    {notice && <div className="workplace-success">{notice}</div>}
    {loading && !data ? <div className="workplace-loading"><IonSpinner/><span>Betriebsdaten werden geladen …</span></div> : null}
    {settings && <IonCard className="workplace-card"><IonCardContent>
      <div className="workplace-head"><div><h3>Betriebseinstellungen</h3><p>Diese Regeln werden von Dienstplanung und Abrechnung verwendet.</p></div>{canSettings && <IonButton size="small" disabled={busy} onClick={saveSettings}>Speichern</IonButton>}</div>
      <div className="workplace-grid">
        <IonInput label="Unternehmen" labelPlacement="stacked" fill="outline" disabled={!canSettings} value={settings.company_name} onIonInput={e=>setSettings({...settings,company_name:String(val(e))})}/>
        <IonSelect label="Zeitzone" labelPlacement="stacked" fill="outline" disabled={!canSettings} value={settings.timezone} onIonChange={e=>setSettings({...settings,timezone:String(val(e))})}><IonSelectOption value="Europe/Berlin">Europe/Berlin</IonSelectOption><IonSelectOption value="UTC">UTC</IonSelectOption><IonSelectOption value="Europe/London">Europe/London</IonSelectOption></IonSelect>
        <IonSelect label="Wochenstart" labelPlacement="stacked" fill="outline" disabled={!canSettings} value={settings.week_starts_on} onIonChange={e=>setSettings({...settings,week_starts_on:Number(val(e))})}>{WEEKDAYS.map((d,i)=><IonSelectOption key={d} value={i}>{d}</IonSelectOption>)}</IonSelect>
        <IonSelect label="Zeitformat" labelPlacement="stacked" fill="outline" disabled={!canSettings} value={settings.time_format} onIonChange={e=>setSettings({...settings,time_format:val(e)})}><IonSelectOption value="24h">24 Stunden</IonSelectOption><IonSelectOption value="12h">12 Stunden</IonSelectOption></IonSelect>
        <IonInput label="Währung" maxlength={3} labelPlacement="stacked" fill="outline" disabled={!canSettings} value={settings.currency} onIonInput={e=>setSettings({...settings,currency:String(val(e)).toUpperCase()})}/>
        <IonSelect label="Überstunden-Regel" labelPlacement="stacked" fill="outline" disabled={!canSettings} value={settings.overtime_mode} onIonChange={e=>setSettings({...settings,overtime_mode:val(e)})}><IonSelectOption value="off">Aus</IonSelectOption><IonSelectOption value="warn">Warnen</IonSelectOption><IonSelectOption value="block">Blockieren</IonSelectOption></IonSelect>
        <IonInput type="number" label="Überstunden ab / Tag (Std.)" labelPlacement="stacked" fill="outline" disabled={!canSettings} value={settings.overtime_daily_hours} onIonInput={e=>setSettings({...settings,overtime_daily_hours:String(val(e))})}/>
        <IonInput type="number" label="Überstunden ab / Woche (Std.)" labelPlacement="stacked" fill="outline" disabled={!canSettings} value={settings.overtime_weekly_hours} onIonInput={e=>setSettings({...settings,overtime_weekly_hours:String(val(e))})}/>
        <IonInput type="number" label="Überstunden-Faktor" labelPlacement="stacked" fill="outline" disabled={!canSettings} value={settings.overtime_multiplier} onIonInput={e=>setSettings({...settings,overtime_multiplier:String(val(e))})}/>
      </div>
      <div className="workplace-toggles"><IonItem lines="none"><IonToggle disabled={!canSettings} checked={settings.labor_sharing_enabled} onIonChange={e=>setSettings({...settings,labor_sharing_enabled:e.detail.checked})}>Labor Sharing aktiv</IonToggle></IonItem><IonItem lines="none"><IonToggle disabled={!canSettings} checked={settings.manager_can_manage_roles} onIonChange={e=>setSettings({...settings,manager_can_manage_roles:e.detail.checked})}>Manager dürfen Rollen verwalten</IonToggle></IonItem></div>
    </IonCardContent></IonCard>}

    <div className="workplace-two-col">
      <IonCard className="workplace-card"><IonCardContent>
        <div className="workplace-head"><div><h3>Rollen</h3><p>Capability-Profile statt pauschalem Manager-Zugriff.</p></div>{canRoles && <IonButton fill="outline" size="small" onClick={()=>editRole()}>Eigene Rolle</IonButton>}</div>
        <div className="role-list">{(data?.roles||[]).map(item=><div className="role-row" key={item.id}><div><div className="role-name"><b>{item.name}</b>{item.is_system && <IonBadge color="light">System</IonBadge>}</div><small>{WAGE_LABEL[item.wage_visibility]} · {item.permissions.length} Rechte · {item.assignment_count} Zuweisungen</small><div className="cap-chips">{item.permissions.slice(0,5).map(p=><span key={p}>{CAP_LABELS[p]||p}</span>)}{item.permissions.length>5&&<span>+{item.permissions.length-5}</span>}</div></div>{canRoles && !item.is_system && <IonButton fill="clear" size="small" onClick={()=>editRole(item)}>Bearbeiten</IonButton>}</div>)}</div>
      </IonCardContent></IonCard>

      <IonCard className="workplace-card"><IonCardContent>
        <div className="workplace-head"><div><h3>Zuweisungen & Scope</h3><p>Wer darf welchen Betriebsteil steuern?</p></div>{canRoles && <IonButton fill="outline" size="small" onClick={()=>editAssignment()}>Zuweisen</IonButton>}</div>
        <div className="assignment-list">{(data?.assignments||[]).map(item=><div className="assignment-row" key={item.id}><div><b>{item.user_name}</b><div className="assignment-meta"><IonBadge color="primary">{item.role_name}</IonBadge><IonBadge color={item.scope_mode==='all'?'success':'warning'}>{item.scope_mode==='all'?'Gesamtbetrieb':'Bereich'}</IonBadge>{item.can_share_labor&&<IonBadge color="tertiary">Labor Sharing</IonBadge>}</div><small>{item.scope_mode==='all'?'Alle Standorte & Teams':[...item.location_names,...item.schedule_names,...item.worker_names].join(' · ')||'Noch kein Scope gewählt'}</small></div>{canRoles&&<IonButton fill="clear" size="small" onClick={()=>editAssignment(item)}>Bearbeiten</IonButton>}</div>)}</div>
      </IonCardContent></IonCard>
    </div>

    <IonCard className="workplace-card"><IonCardContent><div className="workplace-head"><div><h3>Dein effektiver Zugriff</h3><p>Diese Rechte werden serverseitig an jedem geschützten Endpoint geprüft.</p></div><IonBadge color="success">{caps.length} aktiv</IonBadge></div><div className="cap-grid">{caps.map(p=><span key={p}>{CAP_LABELS[p]||p}</span>)}</div></IonCardContent></IonCard>

    <IonModal isOpen={assignmentOpen} onDidDismiss={()=>setAssignmentOpen(false)}><div className="workplace-modal"><div className="workplace-modal-head"><div><small>ROLLE ZUWEISEN</small><h2>{assignmentId?'Zuweisung bearbeiten':'Neue Zuweisung'}</h2></div><IonButton fill="clear" onClick={()=>setAssignmentOpen(false)}>Schließen</IonButton></div><div className="workplace-form">
      <IonSelect label="Benutzer" labelPlacement="stacked" fill="outline" value={assignment.user} onIonChange={e=>setAssignment({...assignment,user:String(val(e))})}>{(data?.managers||[]).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name} · {x.email}</IonSelectOption>)}</IonSelect>
      <IonSelect label="Rolle" labelPlacement="stacked" fill="outline" value={assignment.access_role} onIonChange={e=>setAssignment({...assignment,access_role:String(val(e))})}>{(data?.roles||[]).filter(x=>x.active).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <IonSelect label="Scope" labelPlacement="stacked" fill="outline" value={assignment.scope_mode} onIonChange={e=>setAssignment({...assignment,scope_mode:val(e)})}><IonSelectOption value="all">Gesamter Betrieb</IonSelectOption><IonSelectOption value="scoped">Zugeordnete Bereiche</IonSelectOption></IonSelect>
      {assignment.scope_mode==='scoped'&&<><IonSelect multiple label="Dienstpläne" labelPlacement="stacked" fill="outline" value={assignment.schedule_groups} onIonChange={e=>setAssignment({...assignment,schedule_groups:val(e)||[]})}>{(data?.schedules||[]).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect><IonSelect multiple label="Standorte" labelPlacement="stacked" fill="outline" value={assignment.locations} onIonChange={e=>setAssignment({...assignment,locations:val(e)||[]})}>{(data?.locations||[]).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect><IonSelect multiple label="Einzelne Mitarbeiter" labelPlacement="stacked" fill="outline" value={assignment.workers} onIonChange={e=>setAssignment({...assignment,workers:val(e)||[]})}>{(data?.workers||[]).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name} · {x.employee_number}</IonSelectOption>)}</IonSelect></>}
      <IonItem lines="none"><IonToggle checked={assignment.can_share_labor} onIonChange={e=>setAssignment({...assignment,can_share_labor:e.detail.checked})}>Labor Sharing erlauben</IonToggle></IonItem><IonItem lines="none"><IonToggle checked={assignment.active} onIonChange={e=>setAssignment({...assignment,active:e.detail.checked})}>Zuweisung aktiv</IonToggle></IonItem>
    </div><div className="workplace-modal-actions"><IonButton fill="outline" onClick={()=>setAssignmentOpen(false)}>Abbrechen</IonButton><IonButton disabled={busy||!assignment.user||!assignment.access_role} onClick={saveAssignment}>{busy?<IonSpinner name="dots"/>:'Speichern'}</IonButton></div></div></IonModal>

    <IonModal isOpen={roleOpen} onDidDismiss={()=>setRoleOpen(false)}><div className="workplace-modal"><div className="workplace-modal-head"><div><small>CUSTOM ROLE</small><h2>{roleId?'Rolle bearbeiten':'Eigene Rolle anlegen'}</h2></div><IonButton fill="clear" onClick={()=>setRoleOpen(false)}>Schließen</IonButton></div><div className="workplace-form"><IonInput label="Code" labelPlacement="stacked" fill="outline" value={role.code} onIonInput={e=>setRole({...role,code:String(val(e)).toLowerCase().replace(/[^a-z0-9-]/g,'-')})}/><IonInput label="Name" labelPlacement="stacked" fill="outline" value={role.name} onIonInput={e=>setRole({...role,name:String(val(e))})}/><IonInput label="Beschreibung" labelPlacement="stacked" fill="outline" value={role.description} onIonInput={e=>setRole({...role,description:String(val(e))})}/><IonSelect multiple label="Berechtigungen" labelPlacement="stacked" fill="outline" value={role.permissions} onIonChange={e=>setRole({...role,permissions:val(e)||[]})}>{(data?.capability_catalog||[]).map(p=><IonSelectOption key={p} value={p}>{CAP_LABELS[p]||p}</IonSelectOption>)}</IonSelect><IonSelect label="Lohnsichtbarkeit" labelPlacement="stacked" fill="outline" value={role.wage_visibility} onIonChange={e=>setRole({...role,wage_visibility:val(e)})}><IonSelectOption value="none">Keine Lohndaten</IonSelectOption><IonSelectOption value="scoped">Nur eigener Bereich</IonSelectOption><IonSelectOption value="all">Alle Lohndaten</IonSelectOption></IonSelect><IonItem lines="none"><IonToggle checked={role.active} onIonChange={e=>setRole({...role,active:e.detail.checked})}>Rolle aktiv</IonToggle></IonItem></div><div className="workplace-modal-actions"><IonButton fill="outline" onClick={()=>setRoleOpen(false)}>Abbrechen</IonButton><IonButton disabled={busy||!role.code||!role.name} onClick={saveRole}>{busy?<IonSpinner name="dots"/>:'Speichern'}</IonButton></div></div></IonModal>
  </section>;
}

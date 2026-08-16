import React, { useEffect, useMemo, useState } from 'react';
import { api, me, User } from './api';
import './self-service-v10.css';

type Tab = 'home'|'availability'|'shifts'|'timeoff'|'team'|'review'|'settings';
type Shift = {
  id:string; position_name:string; location_name:string; starts_at:string; ends_at:string; status:string;
  open_count:number; filled_count:number; assignments?:any[]; open_shift_policy?:{require_approval:boolean;audience_mode:string};
  my_open_shift_request?:{id:string;status:string}|null;
};
type Availability = {id:string;kind:string;starts_on:string;ends_on:string;all_day:boolean;start_time?:string|null;end_time?:string|null;recurrence:string;weekdays:number[];note:string;worker_name?:string};
type Coverage = {id:string;kind:'drop'|'swap';status:string;shift:string;shift_position:string;shift_location:string;shift_starts_at:string;requested_by:string;requested_by_name:string;offered_to?:string|null;offered_to_name?:string|null;offered_shift?:string|null;note:string};
type Bid = {id:string;shift:string;position:string;location:string;starts_at:string;worker:string;worker_name:string;status:string;note:string};
type Coworker = {id:string;name:string;email?:string|null;phone?:string|null;contact_hidden:boolean};
type TimeOffType = {id:string;code:string;name:string;allow_paid:boolean;allow_unpaid:boolean};
type TimeOff = {id:string;worker_name:string;starts_on:string;ends_on:string;type_name:string;status:string;all_day:boolean;start_time?:string|null;end_time?:string|null;paid:boolean;paid_hours?:string|null;reason:string};

const unpack=<T,>(value:any):T[] => (value?.results || value || []) as T[];
const day=(offset=0)=>{const d=new Date();d.setDate(d.getDate()+offset);return d.toISOString().slice(0,10)};
const fmt=(value:string)=>new Date(value).toLocaleString('de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const statusLabel=(value:string)=>({pending_review:'Manager-Prüfung',pending_acceptance:'Wartet auf Annahme',pending_approval:'Wartet auf Freigabe',accepted:'Angenommen',denied:'Abgelehnt',declined:'Nicht angenommen',canceled:'Zurückgezogen',approved:'Genehmigt',rejected:'Abgelehnt',pending:'Offen'} as Record<string,string>)[value]||value;

export default function SelfServiceDock(){
  const [user,setUser]=useState<User|null>(null);
  const [open,setOpen]=useState(false);
  const [tab,setTab]=useState<Tab>('home');
  const [snapshot,setSnapshot]=useState<any>(null);
  const [availability,setAvailability]=useState<Availability[]>([]);
  const [mine,setMine]=useState<Shift[]>([]);
  const [available,setAvailable]=useState<Shift[]>([]);
  const [published,setPublished]=useState<Shift[]>([]);
  const [coverage,setCoverage]=useState<Coverage[]>([]);
  const [bids,setBids]=useState<Bid[]>([]);
  const [timeOff,setTimeOff]=useState<TimeOff[]>([]);
  const [coworkers,setCoworkers]=useState<Coworker[]>([]);
  const [directoryVisible,setDirectoryVisible]=useState(true);
  const [team,setTeam]=useState<any[]>([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [reviewTarget,setReviewTarget]=useState<Record<string,string>>({});
  const [swapOffer,setSwapOffer]=useState<Record<string,string>>({});
  const [policyTargets,setPolicyTargets]=useState<Record<string,string[]>>({});
  const [avForm,setAvForm]=useState({kind:'preferred',starts_on:day(7),ends_on:day(35),all_day:true,start_time:'09:00',end_time:'17:00',recurrence:'weekly',weekdays:[new Date(day(7)+'T12:00:00').getDay()===0?6:new Date(day(7)+'T12:00:00').getDay()-1] as number[],note:''});
  const [coverageForm,setCoverageForm]=useState({kind:'drop',shift:'',offered_to:'',note:''});
  const [timeForm,setTimeForm]=useState({type:'',starts_on:day(7),ends_on:day(7),all_day:true,start_time:'09:00',end_time:'13:00',paid:false,paid_hours:'4.00',reason:''});

  const isManager=!!user&&(user.role==='admin'||user.role==='manager');
  const pending=(snapshot?.coverage_pending||0)+(snapshot?.open_shift_requests_pending||0);
  const ownCoverage=useMemo(()=>coverage.filter(row=>user?.role==='worker'&&row.requested_by),[coverage,user]);

  async function bootstrap(){
    if(!localStorage.getItem('access')){setUser(null);return;}
    try{const current=await me();setUser(current);await refresh(current);}catch{setUser(null);}
  }

  async function refresh(current=user){
    if(!current)return;
    setError('');
    const common=await Promise.all([
      api('self-service/snapshot/'),
      api('self-service/availability/').catch(()=>({results:[]})),
      api('self-service/coverage/').catch(()=>({results:[]})),
      api('self-service/open-shift-requests/').catch(()=>({results:[]})),
      api('self-service/time-off/').catch(()=>({results:[]})),
      api('self-service/coworkers/').catch(()=>({visible:false,workers:[]})),
    ]);
    setSnapshot(common[0]); setAvailability(unpack(common[1])); setCoverage(unpack(common[2])); setBids(unpack(common[3])); setTimeOff(unpack(common[4]));
    setDirectoryVisible(common[5]?.visible!==false); setCoworkers(common[5]?.workers||[]);
    const types=(common[0]?.time_off_types||[]) as TimeOffType[];
    if(types.length&&!timeForm.type)setTimeForm(v=>({...v,type:types[0].code}));
    if(current.role==='worker'){
      const [m,a]=await Promise.all([api('shifts/mine/').catch(()=>[]),api('shifts/available/').catch(()=>[])]);
      setMine(unpack(m));setAvailable(unpack(a));
    }else if(current.role==='admin'||current.role==='manager'){
      const rows=await api('shifts/?status=published').catch(()=>[]);setPublished(unpack(rows));
    }
  }

  async function run(task:()=>Promise<any>, success:string){
    setBusy(true);setError('');setNotice('');
    try{await task();setNotice(success);await refresh();}catch(e:any){setError(e?.message||'Aktion fehlgeschlagen.');}finally{setBusy(false);}
  }

  useEffect(()=>{void bootstrap();const auth=()=>void bootstrap();window.addEventListener('auth-lost',auth);window.addEventListener('storage',auth);return()=>{window.removeEventListener('auth-lost',auth);window.removeEventListener('storage',auth)}},[]);
  useEffect(()=>{if(!open||!user)return;void refresh(user)},[open]);

  async function loadTeam(){
    const start=new Date();const end=new Date();end.setDate(end.getDate()+7);
    try{const data:any=await api(`self-service/team-schedule/?starts_at=${encodeURIComponent(start.toISOString())}&ends_at=${encodeURIComponent(end.toISOString())}`);setTeam(data.results||[]);}catch(e:any){setError(e.message);}
  }
  useEffect(()=>{if(open&&tab==='team')void loadTeam()},[open,tab]);

  const createAvailability=()=>run(()=>api('self-service/availability/',{method:'POST',body:JSON.stringify(avForm)}),'Verfügbarkeit gespeichert.');
  const deleteAvailability=(id:string)=>run(()=>api(`self-service/availability/${id}/`,{method:'DELETE'}),'Verfügbarkeit entfernt.');
  const claim=(id:string)=>run(()=>api(`shifts/${id}/claim/`,{method:'POST',body:'{}'}),'OpenShift-Anfrage verarbeitet.');
  const release=(id:string)=>run(()=>api(`shifts/${id}/release/`,{method:'POST',body:'{}'}),'Schicht freigegeben.');
  const createCoverage=()=>run(()=>api('self-service/coverage/',{method:'POST',body:JSON.stringify({...coverageForm,offered_to:coverageForm.offered_to||null})}),'Coverage-Anfrage erstellt.');
  const cancelCoverage=(id:string)=>run(()=>api(`self-service/coverage/${id}/cancel/`,{method:'POST',body:'{}'}),'Anfrage zurückgezogen.');
  const acceptCoverage=(row:Coverage)=>run(()=>api(`self-service/coverage/${row.id}/accept/`,{method:'POST',body:JSON.stringify({offered_shift:row.kind==='swap'?swapOffer[row.id]||null:null})}),'Anfrage angenommen.');
  const declineCoverage=(id:string)=>run(()=>api(`self-service/coverage/${id}/decline/`,{method:'POST',body:'{}'}),'Anfrage abgelehnt.');
  const decideCoverage=(id:string,approve:boolean)=>run(()=>api(`self-service/coverage/${id}/review/`,{method:'POST',body:JSON.stringify({approve,offered_to:reviewTarget[id]||null})}),approve?'Coverage freigegeben.':'Coverage abgelehnt.');
  const decideBid=(id:string,approve:boolean)=>run(()=>api(`self-service/open-shift-requests/${id}/decide/`,{method:'POST',body:JSON.stringify({approve})}),approve?'OpenShift vergeben.':'Bewerbung abgelehnt.');
  const cancelBid=(id:string)=>run(()=>api(`self-service/open-shift-requests/${id}/cancel/`,{method:'POST',body:'{}'}),'Bewerbung zurückgezogen.');
  const savePreference=(patch:any)=>run(()=>api('self-service/preference/',{method:'PATCH',body:JSON.stringify(patch)}),'Einstellung gespeichert.');
  const saveSettings=(patch:any)=>run(()=>api('self-service/settings/',{method:'PATCH',body:JSON.stringify(patch)}),'Self-Service-Regel gespeichert.');
  const createTimeOff=()=>run(()=>api('self-service/time-off/',{method:'POST',body:JSON.stringify(timeForm)}),'Abwesenheitsanfrage gesendet.');
  const savePolicy=(shift:Shift,patch:any)=>run(()=>api(`self-service/open-shifts/${shift.id}/policy/`,{method:'PATCH',body:JSON.stringify(patch)}),'OpenShift-Policy gespeichert.');

  if(!user)return null;
  const workerTabs:[Tab,string][]=[['home','Übersicht'],['availability','Verfügbarkeit'],['shifts','Schichten'],['timeoff','Abwesenheit'],['team','Team & Datenschutz']];
  const managerTabs:[Tab,string][]=[['home','Übersicht'],['review','Anfragen'],['settings','Self-Service Regeln'],['team','Teamplan']];
  const tabs=isManager?managerTabs:workerTabs;

  return <>
    <button className="ss-launcher" data-testid="self-service-launcher" onClick={()=>setOpen(true)} aria-label="Self-Service öffnen">
      <span>⇄</span><b>Self-Service</b>{pending>0&&<i>{pending}</i>}
    </button>
    {open&&<div className="ss-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setOpen(false)}}>
      <section className="ss-shell" role="dialog" aria-label="Self-Service" data-testid="self-service-panel">
        <header className="ss-head"><div><small>A+ WORKFORCE · SELF-SERVICE</small><h2>{isManager?'Employee Self-Service Steuerung':'Meine Arbeit organisieren'}</h2><p>{isManager?'Freigaben, Coverage, OpenShift und Richtlinien zentral verwalten.':'Verfügbarkeit, offene Schichten, Tausch und Abwesenheit ohne Umwege.'}</p></div><button onClick={()=>setOpen(false)}>✕</button></header>
        <nav className="ss-tabs">{tabs.map(([key,label])=><button key={key} className={tab===key?'active':''} onClick={()=>setTab(key)}>{label}{key==='review'&&pending>0?<em>{pending}</em>:null}</button>)}</nav>
        {error&&<div className="ss-alert error">{error}</div>}{notice&&<div className="ss-alert success">{notice}</div>}

        {tab==='home'&&<div className="ss-page">
          <div className="ss-kpis"><article><span>Coverage</span><b>{snapshot?.coverage_pending||0}</b><small>offene Vorgänge</small></article><article><span>OpenShift</span><b>{snapshot?.open_shift_requests_pending||0}</b><small>wartende Anfragen</small></article><article><span>Privacy</span><b>{snapshot?.settings?.global_user_privacy?'Global':'Individuell'}</b><small>Kontaktsichtbarkeit</small></article><article><span>Teamplan</span><b>{snapshot?.settings?.team_schedule_visibility||'none'}</b><small>Sichtbarkeit</small></article></div>
          <div className="ss-card"><h3>{isManager?'Aktive Self-Service-Regeln':'Was kann ich hier tun?'}</h3><div className="ss-rule-grid"><span>Verfügbarkeit <b>{snapshot?.settings?.availability_enabled?'aktiv':'aus'}</b></span><span>Release <b>{snapshot?.settings?.allow_shift_release?'aktiv':'aus'}</b></span><span>Drop <b>{snapshot?.settings?.allow_shift_drop?'aktiv':'aus'}</b></span><span>Swap <b>{snapshot?.settings?.allow_shift_swap?'aktiv':'aus'}</b></span><span>Time Off <b>{snapshot?.settings?.time_off_enabled?'aktiv':'aus'}</b></span><span>Manager Review <b>{snapshot?.settings?.require_manager_review_swaps_drops?'erforderlich':'direkt'}</b></span></div></div>
        </div>}

        {tab==='availability'&&!isManager&&<div className="ss-page two">
          <div className="ss-card"><h3>Verfügbarkeit eintragen</h3><label>Art<select value={avForm.kind} onChange={e=>setAvForm({...avForm,kind:e.target.value})}><option value="preferred">Bevorzugt</option><option value="unavailable">Nicht verfügbar</option></select></label><div className="ss-row"><label>Von<input type="date" value={avForm.starts_on} onChange={e=>setAvForm({...avForm,starts_on:e.target.value})}/></label><label>Bis<input type="date" value={avForm.ends_on} onChange={e=>setAvForm({...avForm,ends_on:e.target.value})}/></label></div><label>Wiederholung<select value={avForm.recurrence} onChange={e=>setAvForm({...avForm,recurrence:e.target.value})}><option value="once">Einmalig</option><option value="daily">Täglich</option><option value="weekly">Wöchentlich</option><option value="two_weeks">Alle 2 Wochen</option></select></label>{['weekly','two_weeks'].includes(avForm.recurrence)&&<div className="ss-weekdays">{['Mo','Di','Mi','Do','Fr','Sa','So'].map((d,i)=><button key={d} className={avForm.weekdays.includes(i)?'active':''} onClick={()=>setAvForm({...avForm,weekdays:avForm.weekdays.includes(i)?avForm.weekdays.filter(x=>x!==i):[...avForm.weekdays,i]})}>{d}</button>)}</div>}<label className="ss-check"><input type="checkbox" checked={avForm.all_day} onChange={e=>setAvForm({...avForm,all_day:e.target.checked})}/> Ganztägig</label>{!avForm.all_day&&<div className="ss-row"><label>Start<input type="time" value={avForm.start_time} onChange={e=>setAvForm({...avForm,start_time:e.target.value})}/></label><label>Ende<input type="time" value={avForm.end_time} onChange={e=>setAvForm({...avForm,end_time:e.target.value})}/></label></div>}<label>Notiz<input value={avForm.note} onChange={e=>setAvForm({...avForm,note:e.target.value})}/></label><button className="primary" disabled={busy} onClick={()=>void createAvailability()}>Speichern</button></div>
          <div className="ss-card"><h3>Meine Regeln</h3>{availability.map(row=><article className="ss-list-row" key={row.id}><div><b>{row.kind==='preferred'?'Bevorzugt':'Nicht verfügbar'}</b><small>{row.starts_on} – {row.ends_on} · {row.recurrence.replace('_',' ')}</small><p>{row.note||'Keine Notiz'}</p></div><button onClick={()=>void deleteAvailability(row.id)}>Entfernen</button></article>)}{!availability.length&&<p className="ss-empty">Noch keine Verfügbarkeitsregeln.</p>}</div>
        </div>}

        {tab==='shifts'&&!isManager&&<div className="ss-page">
          <div className="ss-grid2"><div className="ss-card"><h3>Offene Schichten</h3>{available.map(shift=><article className="ss-shift" key={shift.id}><div><b>{shift.position_name}</b><small>{fmt(shift.starts_at)} · {shift.location_name}</small><span>{shift.open_shift_policy?.require_approval?'Bewerbung + Freigabe':'Direkt übernehmen'}</span></div><button className="primary" disabled={busy||shift.my_open_shift_request?.status==='pending_approval'} onClick={()=>void claim(shift.id)}>{shift.my_open_shift_request?.status==='pending_approval'?'Angefragt':'Übernehmen'}</button></article>)}{!available.length&&<p className="ss-empty">Keine passenden OpenShifts.</p>}{bids.filter(x=>x.status==='pending_approval').map(row=><article className="ss-list-row" key={row.id}><div><b>Bewerbung: {row.position}</b><small>{fmt(row.starts_at)} · {row.location}</small></div><button onClick={()=>void cancelBid(row.id)}>Zurückziehen</button></article>)}</div><div className="ss-card"><h3>Meine Schichten</h3>{mine.map(shift=><article className="ss-shift" key={shift.id}><div><b>{shift.position_name}</b><small>{fmt(shift.starts_at)} · {shift.location_name}</small></div><button disabled={busy} onClick={()=>void release(shift.id)}>Freigeben</button></article>)}{!mine.length&&<p className="ss-empty">Keine kommenden Schichten.</p>}</div></div>
          <div className="ss-card"><h3>Schicht abgeben oder tauschen</h3><div className="ss-row three"><label>Aktion<select value={coverageForm.kind} onChange={e=>setCoverageForm({...coverageForm,kind:e.target.value})}><option value="drop">Drop / Abgeben</option><option value="swap">Swap / Tauschen</option></select></label><label>Eigene Schicht<select value={coverageForm.shift} onChange={e=>setCoverageForm({...coverageForm,shift:e.target.value})}><option value="">Auswählen</option>{mine.map(s=><option key={s.id} value={s.id}>{s.position_name} · {fmt(s.starts_at)}</option>)}</select></label><label>Zielmitarbeiter<select value={coverageForm.offered_to} onChange={e=>setCoverageForm({...coverageForm,offered_to:e.target.value})}><option value="">Manager soll wählen</option>{coworkers.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label></div><label>Notiz<input value={coverageForm.note} onChange={e=>setCoverageForm({...coverageForm,note:e.target.value})}/></label><button className="primary" disabled={busy||!coverageForm.shift||(coverageForm.kind==='swap'&&!coverageForm.offered_to)} onClick={()=>void createCoverage()}>Anfrage senden</button></div>
          <div className="ss-card"><h3>Coverage-Vorgänge</h3>{coverage.map(row=><article className="ss-list-row" key={row.id}><div><b>{row.kind==='swap'?'Swap':'Drop'} · {row.shift_position}</b><small>{fmt(row.shift_starts_at)} · {statusLabel(row.status)}</small><p>{row.offered_to_name?`Ziel: ${row.offered_to_name}`:'Noch kein Zielmitarbeiter'}</p></div><div className="ss-actions">{row.status==='pending_acceptance'&&row.offered_to&&row.requested_by!==user.id&&<>{row.kind==='swap'&&<select value={swapOffer[row.id]||''} onChange={e=>setSwapOffer({...swapOffer,[row.id]:e.target.value})}><option value="">Gegenschicht wählen</option>{mine.filter(s=>s.id!==row.shift).map(s=><option key={s.id} value={s.id}>{s.position_name} · {fmt(s.starts_at)}</option>)}</select>}<button className="primary" onClick={()=>void acceptCoverage(row)} disabled={row.kind==='swap'&&!swapOffer[row.id]}>Annehmen</button><button onClick={()=>void declineCoverage(row.id)}>Ablehnen</button></>}{['pending_review','pending_acceptance'].includes(row.status)&&<button onClick={()=>void cancelCoverage(row.id)}>Zurückziehen</button>}</div></article>)}{!coverage.length&&<p className="ss-empty">Keine Coverage-Anfragen.</p>}</div>
        </div>}

        {tab==='timeoff'&&!isManager&&<div className="ss-page two"><div className="ss-card"><h3>Abwesenheit beantragen</h3><label>Typ<select value={timeForm.type} onChange={e=>setTimeForm({...timeForm,type:e.target.value})}>{(snapshot?.time_off_types||[]).map((t:TimeOffType)=><option key={t.id} value={t.code}>{t.name}</option>)}</select></label><div className="ss-row"><label>Von<input type="date" value={timeForm.starts_on} onChange={e=>setTimeForm({...timeForm,starts_on:e.target.value})}/></label><label>Bis<input type="date" value={timeForm.ends_on} onChange={e=>setTimeForm({...timeForm,ends_on:e.target.value})}/></label></div><label className="ss-check"><input type="checkbox" checked={timeForm.all_day} onChange={e=>setTimeForm({...timeForm,all_day:e.target.checked})}/> Ganztägig</label>{!timeForm.all_day&&<div className="ss-row"><label>Start<input type="time" value={timeForm.start_time} onChange={e=>setTimeForm({...timeForm,start_time:e.target.value})}/></label><label>Ende<input type="time" value={timeForm.end_time} onChange={e=>setTimeForm({...timeForm,end_time:e.target.value})}/></label></div>}<label className="ss-check"><input type="checkbox" checked={timeForm.paid} onChange={e=>setTimeForm({...timeForm,paid:e.target.checked})}/> Bezahlt</label>{timeForm.paid&&<label>Bezahlte Stunden<input type="number" min="0" step="0.25" value={timeForm.paid_hours} onChange={e=>setTimeForm({...timeForm,paid_hours:e.target.value})}/></label>}<label>Grund<textarea value={timeForm.reason} onChange={e=>setTimeForm({...timeForm,reason:e.target.value})}/></label><button className="primary" disabled={busy||!timeForm.type} onClick={()=>void createTimeOff()}>Anfrage senden</button></div><div className="ss-card"><h3>Meine Abwesenheiten</h3>{timeOff.map(row=><article className="ss-list-row" key={row.id}><div><b>{row.type_name}</b><small>{row.starts_on} – {row.ends_on} · {statusLabel(row.status)}</small><p>{row.all_day?'Ganztägig':`${row.start_time}–${row.end_time}`}{row.paid?` · bezahlt ${row.paid_hours||''} Std.`:''}</p></div></article>)}{!timeOff.length&&<p className="ss-empty">Noch keine Abwesenheitsanfragen.</p>}</div></div>}

        {tab==='team'&&<div className="ss-page two"><div className="ss-card"><h3>Teamplan · nächste 7 Tage</h3>{team.map(row=><article className="ss-list-row" key={row.id}><div><b>{row.position}</b><small>{fmt(row.starts_at)} · {row.location}</small><p>{row.workers?.join(', ')||'Noch unbesetzt'}</p></div></article>)}{!team.length&&<p className="ss-empty">Kein Teamplan sichtbar oder keine Schichten im Zeitraum.</p>}</div><div className="ss-card"><h3>{isManager?'Mitarbeiterverzeichnis':'Datenschutz & Kontakte'}</h3>{!isManager&&<><label className="ss-check"><input type="checkbox" checked={!!snapshot?.preference?.hide_contact_info} disabled={snapshot?.settings?.global_user_privacy} onChange={e=>void savePreference({hide_contact_info:e.target.checked})}/> Meine Kontaktdaten verbergen</label><label>Bevorzugte Wochenstunden<input type="number" min="0" step="0.5" value={snapshot?.preference?.preferred_weekly_hours||''} onChange={e=>setSnapshot((s:any)=>({...s,preference:{...s.preference,preferred_weekly_hours:e.target.value}}))} onBlur={e=>void savePreference({preferred_weekly_hours:e.target.value||null})}/></label></>}{directoryVisible?coworkers.map(row=><article className="ss-person" key={row.id}><b>{row.name}</b><small>{row.contact_hidden?'Kontaktdaten privat':[row.email,row.phone].filter(Boolean).join(' · ')}</small></article>):<p className="ss-empty">Das Mitarbeiterverzeichnis ist durch globale Privacy deaktiviert.</p>}</div></div>}

        {tab==='review'&&isManager&&<div className="ss-page two"><div className="ss-card"><h3>OpenShift Bewerbungen</h3>{bids.filter(x=>x.status==='pending_approval').map(row=><article className="ss-list-row" key={row.id}><div><b>{row.worker_name}</b><small>{row.position} · {fmt(row.starts_at)} · {row.location}</small><p>{row.note||'Keine Notiz'}</p></div><div className="ss-actions"><button className="primary" onClick={()=>void decideBid(row.id,true)}>Genehmigen</button><button onClick={()=>void decideBid(row.id,false)}>Ablehnen</button></div></article>)}{!bids.some(x=>x.status==='pending_approval')&&<p className="ss-empty">Keine offenen Bewerbungen.</p>}</div><div className="ss-card"><h3>Drop / Swap Prüfung</h3>{coverage.filter(x=>x.status==='pending_review').map(row=><article className="ss-list-row" key={row.id}><div><b>{row.requested_by_name} · {row.kind==='swap'?'Swap':'Drop'}</b><small>{row.shift_position} · {fmt(row.shift_starts_at)}</small><p>{row.note||'Keine Notiz'}</p></div><div className="ss-actions"><select value={reviewTarget[row.id]||row.offered_to||''} onChange={e=>setReviewTarget({...reviewTarget,[row.id]:e.target.value})}><option value="">Zielmitarbeiter wählen</option>{coworkers.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select><button className="primary" disabled={!(reviewTarget[row.id]||row.offered_to)} onClick={()=>void decideCoverage(row.id,true)}>Freigeben</button><button onClick={()=>void decideCoverage(row.id,false)}>Ablehnen</button></div></article>)}{!coverage.some(x=>x.status==='pending_review')&&<p className="ss-empty">Keine offenen Coverage-Prüfungen.</p>}</div></div>}

        {tab==='settings'&&isManager&&<div className="ss-page">
          <div className="ss-card"><h3>Employee Self-Service Policies</h3><div className="ss-settings-grid"><SettingToggle label="Verfügbarkeit durch Mitarbeiter" value={!!snapshot?.settings?.availability_enabled} onChange={v=>saveSettings({availability_enabled:v})}/><SettingToggle label="Verfügbarkeit teamweit sichtbar" value={!!snapshot?.settings?.show_availability_to_all} onChange={v=>saveSettings({show_availability_to_all:v})}/><SettingToggle label="Global User Privacy" value={!!snapshot?.settings?.global_user_privacy} onChange={v=>saveSettings({global_user_privacy:v})}/><SettingToggle label="Shift Release" value={!!snapshot?.settings?.allow_shift_release} onChange={v=>saveSettings({allow_shift_release:v})}/><SettingToggle label="Shift Drop" value={!!snapshot?.settings?.allow_shift_drop} onChange={v=>saveSettings({allow_shift_drop:v})}/><SettingToggle label="Shift Swap" value={!!snapshot?.settings?.allow_shift_swap} onChange={v=>saveSettings({allow_shift_swap:v})}/><SettingToggle label="Manager Review für Drop/Swap" value={!!snapshot?.settings?.require_manager_review_swaps_drops} onChange={v=>saveSettings({require_manager_review_swaps_drops:v})}/><SettingToggle label="Time Off Requests" value={!!snapshot?.settings?.time_off_enabled} onChange={v=>saveSettings({time_off_enabled:v})}/></div><div className="ss-row four"><NumberSetting label="Availability Vorlauf (Tage)" value={snapshot?.settings?.availability_notice_days} onSave={v=>saveSettings({availability_notice_days:v})}/><NumberSetting label="Release Cutoff (Std.)" value={snapshot?.settings?.release_cutoff_hours} onSave={v=>saveSettings({release_cutoff_hours:v})}/><NumberSetting label="Drop Cutoff (Std.)" value={snapshot?.settings?.drop_cutoff_hours} onSave={v=>saveSettings({drop_cutoff_hours:v})}/><NumberSetting label="Swap Cutoff (Std.)" value={snapshot?.settings?.swap_cutoff_hours} onSave={v=>saveSettings({swap_cutoff_hours:v})}/><NumberSetting label="Time Off Vorlauf (Tage)" value={snapshot?.settings?.time_off_notice_days} onSave={v=>saveSettings({time_off_notice_days:v})}/><NumberSetting label="Max. bezahlte Std./Tag" value={snapshot?.settings?.time_off_max_paid_hours_per_day} step="0.25" onSave={v=>saveSettings({time_off_max_paid_hours_per_day:v})}/><label>Teamplan Sichtbarkeit<select value={snapshot?.settings?.team_schedule_visibility||'none'} onChange={e=>void saveSettings({team_schedule_visibility:e.target.value})}><option value="none">Nur eigene Schichten</option><option value="positions">Gemeinsame Positionen</option><option value="all">Gesamter Teamplan</option></select></label></div></div>
          <div className="ss-card"><h3>OpenShift Policies</h3>{published.filter(s=>(s.open_count||0)>0).map(shift=><article className="ss-policy" key={shift.id}><div><b>{shift.position_name}</b><small>{fmt(shift.starts_at)} · {shift.location_name}</small></div><label className="ss-check"><input type="checkbox" checked={!!shift.open_shift_policy?.require_approval} onChange={e=>void savePolicy(shift,{require_approval:e.target.checked})}/> Manager-Freigabe</label><select value={shift.open_shift_policy?.audience_mode||'eligible'} onChange={e=>void savePolicy(shift,{audience_mode:e.target.value,selected_workers:e.target.value==='selected'?(policyTargets[shift.id]||[]):[]})}><option value="eligible">Alle berechtigten</option><option value="selected">Ausgewählte Mitarbeiter</option></select>{shift.open_shift_policy?.audience_mode==='selected'&&<select multiple value={policyTargets[shift.id]||[]} onChange={e=>{const values=Array.from(e.target.selectedOptions).map(o=>o.value);setPolicyTargets({...policyTargets,[shift.id]:values});void savePolicy(shift,{audience_mode:'selected',selected_workers:values})}}>{coworkers.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select>}</article>)}{!published.some(s=>(s.open_count||0)>0)&&<p className="ss-empty">Keine veröffentlichten OpenShifts.</p>}</div>
        </div>}
      </section>
    </div>}
  </>;
}

function SettingToggle({label,value,onChange}:{label:string;value:boolean;onChange:(value:boolean)=>void}){return <label className="ss-setting-toggle"><span>{label}</span><input type="checkbox" checked={value} onChange={e=>onChange(e.target.checked)}/></label>}
function NumberSetting({label,value,onSave,step='1'}:{label:string;value:any;onSave:(value:number)=>void;step?:string}){const [local,setLocal]=useState(value??0);useEffect(()=>setLocal(value??0),[value]);return <label>{label}<input type="number" min="0" step={step} value={local} onChange={e=>setLocal(e.target.value)} onBlur={()=>onSave(Number(local||0))}/></label>}

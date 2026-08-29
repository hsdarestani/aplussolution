import React, { useEffect, useMemo, useState } from 'react';
import { IonAlert, IonBadge, IonButton, IonIcon, IonInput, IonLabel, IonModal, IonSearchbar, IonSegment, IonSegmentButton, IonSelect, IonSelectOption, IonTextarea, IonToast, IonToggle } from '@ionic/react';
import { addOutline, briefcaseOutline, businessOutline, checkmarkCircleOutline, locationOutline, peopleOutline, personCircleOutline, refreshOutline, timeOutline } from 'ionicons/icons';
import { api, User } from './api';
import { akteHref, openAkte, AkteKind } from './entityNavigation';
import { enrichLocationPayload } from './locationPicker';
import './schedule-v2.css';

const unpack = (x:any):any[] => x?.results || x || [];
const val = (e:any) => e.detail.value ?? '';
const isManager = (u:User) => ['admin','manager'].includes(u.role);
const BERLIN_TIME_ZONE = 'Europe/Berlin';
const berlinFormatter = (options:Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('de-DE',{timeZone:BERLIN_TIME_ZONE,...options});
const tm = (x:string) => berlinFormatter({hour:'2-digit',minute:'2-digit'}).format(new Date(x));
const berlinDay = (x:string) => berlinFormatter({day:'numeric'}).format(new Date(x));
const berlinMonth = (x:string) => berlinFormatter({month:'short'}).format(new Date(x));
const workerLabel = (worker:any) => worker?.user_detail?.name || worker?.user_detail?.email || worker?.employee_number || 'Mitarbeiter';
const isSyntheticWorker = (worker:any) => String(worker?.user_detail?.email || '').toLowerCase().endsWith('@sync.invalid');
const pad = (value:number) => String(value).padStart(2,'0');
const berlinDate = (offsetDays=0) => {
  const now = new Date();
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:BERLIN_TIME_ZONE,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
  const values = Object.fromEntries(parts.filter(part=>part.type!=='literal').map(part=>[part.type,part.value]));
  const base = new Date(Date.UTC(Number(values.year),Number(values.month)-1,Number(values.day)+offsetDays));
  return `${base.getUTCFullYear()}-${pad(base.getUTCMonth()+1)}-${pad(base.getUTCDate())}`;
};
const splitDateTime = (input?:string) => {
  const [date='',rest=''] = String(input||'').split('T');
  return {date,time:rest.slice(0,5)};
};
const joinDateTime = (date:string,time:string) => date&&time?`${date}T${time}`:'';
const wallClockMs = (input:string) => {
  const {date,time}=splitDateTime(input);
  const [year,month,day]=date.split('-').map(Number);
  const [hour,minute]=time.split(':').map(Number);
  return Date.UTC(year,month-1,day,hour,minute);
};
const fromWallClockMs = (value:number) => {
  const date = new Date(value);
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth()+1)}-${pad(date.getUTCDate())}T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`;
};
const keyToDate = (key:string) => {
  const [year,month,day]=key.split('-').map(Number);
  return new Date(Date.UTC(year,month-1,day,12));
};
const keyFromDate = (date:Date) => `${date.getUTCFullYear()}-${pad(date.getUTCMonth()+1)}-${pad(date.getUTCDate())}`;
const addKeyDays = (key:string,days:number) => { const date=keyToDate(key); date.setUTCDate(date.getUTCDate()+days); return keyFromDate(date); };
const addKeyMonths = (key:string,months:number) => { const date=keyToDate(key); date.setUTCDate(1); date.setUTCMonth(date.getUTCMonth()+months); return keyFromDate(date); };
const startOfWeekKey = (key:string) => { const day=keyToDate(key).getUTCDay(); return addKeyDays(key,day===0?-6:1-day); };
const shiftDateKey = (input:string) => {
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:BERLIN_TIME_ZONE,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(input));
  const values = Object.fromEntries(parts.filter(part=>part.type!=='literal').map(part=>[part.type,part.value]));
  return `${values.year}-${values.month}-${values.day}`;
};
const keyLabel = (key:string,options:Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('de-DE',{timeZone:BERLIN_TIME_ZONE,...options}).format(keyToDate(key));
const statusInfo = (x:any) => {
  const open=x.status==='published'&&Number(x.open_count||0)>0;
  return {open,label:x.status==='draft'?'Entwurf':open?'Offen':'Voll',color:x.status==='draft'?'medium':open?'primary':'success'};
};
const clientKey = (item:any) => String(item?.client || item?.client_name || 'ohne-kunde');
const workerInitials = (worker:any) => String(worker?.name || worker?.employee_number || 'MA').trim().split(/\s+/).slice(0,2).map((part:string)=>part[0]||'').join('').toUpperCase() || 'MA';
const serviceText = (item:any) => `${item?.position_name||''} ${item?.order_title||''} ${item?.client_name||''} ${item?.location_name||''}`.toLocaleLowerCase('de-DE');
type ScheduleView = 'list'|'day'|'week'|'month'|'timeline';
type ServiceFilter = 'all'|'service'|'hotel'|'housekeeping';
const matchesServiceFilter = (item:any, filter:ServiceFilter) => {
  if(filter==='all') return true;
  const text=serviceText(item);
  if(filter==='housekeeping') return /house\s*keeping|zimmerreinigung|zimmermädchen|roomboy|reinigung/.test(text);
  if(filter==='hotel') return /hotel|hotellerie|rezeption|reception|front\s*office/.test(text);
  return /service|servicekraft|kellner|kellnerin|gastronomie|bankett|banquet/.test(text);
};

const automaticBreakMinutes=(startsAt?:string,endsAt?:string)=>{if(!startsAt||!endsAt)return 0;const hours=(wallClockMs(endsAt)-wallClockMs(startsAt))/3600000;if(hours>=11)return 60;if(hours>=9)return 45;if(hours>=6)return 30;return 0;};
const NOTE_TEMPLATES:[string,string][]=[
  ['', 'Textvorlage auswählen …'],
  ['uniform','Bitte pünktlich erscheinen und auf vollständige, saubere Arbeitskleidung achten.'],
  ['contact','Bitte 10 Minuten vor Einsatzbeginn vor Ort sein und sich bei der Einsatzleitung melden.'],
  ['documents','Bitte Ausweis und alle für den Einsatz erforderlichen Unterlagen mitbringen.'],
  ['hotel','Bitte gepflegte schwarze Kleidung und schwarze, geschlossene Schuhe tragen.'],
];
const SCHEDULE_GROUPS:[string,string][]=[['service','Service'],['front_office','Front Office'],['housekeeping','Housekeeping']];
const scheduleGroupsForClient=(name?:string)=>/hotel\s*spenerhaus/i.test(String(name||''))?['front_office','housekeeping']:[];
const scheduleGroupsForPosition=(name?:string)=>/house\s*keeping/i.test(String(name||''))?['housekeeping']:/front[-\s]*office/i.test(String(name||''))?['front_office']:/service|bar-support/i.test(String(name||''))?['service']:[];

function FriendlyDateTime({label,value,onChange}:{label:string;value?:string;onChange:(next:string)=>void}) {
  const quick=(offset:number)=>{const date=berlinDate(offset);const time=splitDateTime(value).time||'09:00';onChange(joinDateTime(date,time));};
  return <div className="sv2-datetime" data-testid={`datetime-${label.toLowerCase()}`}>
    <div className="sv2-datetime-head"><b>{label} *</b><div className="sv2-date-shortcuts"><IonButton size="small" fill="clear" onClick={()=>quick(0)}>Heute</IonButton><IonButton size="small" fill="clear" onClick={()=>quick(1)}>Morgen</IonButton></div></div>
    <IonInput aria-label={`${label} Datum und Uhrzeit`} fill="outline" type="datetime-local" step="900" label="Datum & Uhrzeit" labelPlacement="floating" value={value||''} onIonInput={e=>onChange(String(val(e)))}/>
  </div>;
}

export default function ScheduleV2({user}:{user:User}) {
  const [rows,setRows]=useState<any[]>([]), [clients,setClients]=useState<any[]>([]), [locations,setLocations]=useState<any[]>([]), [positions,setPositions]=useState<any[]>([]), [workers,setWorkers]=useState<any[]>([]);
  const [tab,setTab]=useState(user.role==='worker'?'available':'open'), [search,setSearch]=useState(''), [modal,setModal]=useState(false), [editing,setEditing]=useState<string>(), [busy,setBusy]=useState(false), [toast,setToast]=useState('');
  const [form,setForm]=useState<any>({required_count:1,break_minutes:0,publish_now:true,confirmation_required:false,workers:[]});
  const [releaseTarget,setReleaseTarget]=useState<any>();
  const [view,setView]=useState<ScheduleView>(()=>typeof window!=='undefined'&&window.matchMedia('(max-width: 900px)').matches?'day':'list');
  const [anchor,setAnchor]=useState(berlinDate());
  const [serviceFilter,setServiceFilter]=useState<ServiceFilter>('all');
  const [aiOpen,setAiOpen]=useState(false), [orderText,setOrderText]=useState(''), [parsedOrder,setParsedOrder]=useState<any>();
  const [locationOpen,setLocationOpen]=useState(false), [locationForm,setLocationForm]=useState<any>({geofence_radius_m:250});

  async function load() {
    const q=search.trim()?`&search=${encodeURIComponent(search.trim())}`:'';
    if(user.role==='worker') { const endpoint=tab==='mine'?'shifts/mine/':'shifts/available/'; setRows(unpack(await api(`${endpoint}?ordering=starts_at${q}`))); return; }
    if(user.role==='client') { setRows(unpack(await api(`shifts/?ordering=starts_at${q}`))); return; }
    const [s,c,l,p,w]=await Promise.all([api(`shifts/?ordering=starts_at${q}`),api('clients/'),api('locations/'),api('positions/'),api('workers/?ordering=user__last_name')]);
    setRows(unpack(s)); setClients(unpack(c).filter((item:any)=>item.active!==false)); setLocations(unpack(l).filter((item:any)=>item.active!==false)); setPositions(unpack(p).filter((item:any)=>item.active!==false)); setWorkers(unpack(w).filter((item:any)=>item.active!==false&&!isSyntheticWorker(item)));
  }
  useEffect(()=>{void load();},[tab]);

  const clientHueMap=useMemo(()=>{
    const keys=Array.from(new Set(rows.map(clientKey))).sort();
    return new Map(keys.map((key,index)=>[key,(18+index*137.508)%360]));
  },[rows]);
  const clientStyle=(item:any)=>({'--sv2-client-hue':String(item?.color_hue ?? clientHueMap.get(clientKey(item)) ?? 215)} as React.CSSProperties);

  const visible=useMemo(()=>rows.filter((x:any)=>{
    if(!matchesServiceFilter(x,serviceFilter)) return false;
    if(user.role==='client') return true;
    if(!isManager(user)||tab==='all') return true;
    if(x.ends_at && new Date(x.ends_at).getTime()<Date.now()) return false;
    if(tab==='draft') return x.status==='draft';
    if(tab==='filled') return x.status!=='draft'&&Number(x.open_count||0)===0;
    return x.status==='published'&&Number(x.open_count||0)>0;
  }),[rows,tab,user,serviceFilter]);

  const clientLegend=useMemo(()=>{
    const map=new Map<string,any>();
    for(const item of visible) if(!map.has(clientKey(item))) map.set(clientKey(item),item);
    return Array.from(map.values()).sort((a,b)=>String(a.client_name||'').localeCompare(String(b.client_name||''),'de'));
  },[visible]);
  const weekStart=startOfWeekKey(anchor);
  const weekDays=useMemo(()=>Array.from({length:7},(_,index)=>addKeyDays(weekStart,index)),[weekStart]);
  const monthStart=useMemo(()=>{const date=keyToDate(anchor);date.setUTCDate(1);return keyFromDate(date);},[anchor]);
  const monthGridStart=useMemo(()=>{const day=keyToDate(monthStart).getUTCDay();return addKeyDays(monthStart,-(day===0?6:day-1));},[monthStart]);
  const monthDays=useMemo(()=>Array.from({length:42},(_,index)=>addKeyDays(monthGridStart,index)),[monthGridStart]);
  const rowsByDay=useMemo(()=>{const map:Record<string,any[]>={}; for(const item of visible){const key=shiftDateKey(item.starts_at);(map[key] ||= []).push(item);} return map;},[visible]);
  const timelineLocations=useMemo(()=>Array.from(new Set(visible.filter(x=>weekDays.includes(shiftDateKey(x.starts_at))).map(x=>x.location_name||'Ohne Einsatzort'))).sort(),[visible,weekDays]);
  const weekTotalHours=useMemo(()=>visible.filter(x=>weekDays.includes(shiftDateKey(x.starts_at))).reduce((sum:number,x:any)=>{const gross=Math.max(0,(new Date(x.ends_at).getTime()-new Date(x.starts_at).getTime())/3600000);return sum+Math.max(0,gross-Number(x.break_minutes||0)/60);},0),[visible,weekDays]);

  async function act(path:string,msg:string){setBusy(true);try{await api(path,{method:'POST',body:'{}'});setToast(msg);await load();}catch(e:any){setToast(e.message);}finally{setBusy(false);}}
  function create(){setEditing(undefined);setForm({required_count:1,break_minutes:0,publish_now:true,confirmation_required:false,workers:[],schedule_groups:[]});setModal(true);}
  function edit(x:any){setEditing(x.id);setForm({...x,workers:(x.assigned_workers||[]).map((worker:any)=>worker.id),schedule_groups:x.schedule_groups||[],starts_at:x.starts_at?.slice(0,16),ends_at:x.ends_at?.slice(0,16),publish_now:x.status==='published'});setModal(true);}
  function setShiftDateTime(field:'starts_at'|'ends_at',next:string){setForm((current:any)=>{const updated={...current,[field]:next};if(field==='starts_at'&&next){const start=wallClockMs(next);const currentEnd=current.ends_at?wallClockMs(current.ends_at):undefined;if(!currentEnd||currentEnd<=start)updated.ends_at=fromWallClockMs(start+4*60*60*1000);}updated.break_minutes=automaticBreakMinutes(updated.starts_at,updated.ends_at);return updated;});}
  async function saveInlineLocation(){if(!form.client){setToast('Bitte zuerst einen Kunden auswählen.');return;}if(!locationForm.name||!locationForm.address){setToast('Bitte Bezeichnung und Adresse eingeben.');return;}setBusy(true);try{const payload=await enrichLocationPayload({...locationForm,client:form.client});const saved:any=await api('locations/',{method:'POST',body:JSON.stringify(payload)});setLocations(current=>[...current.filter(item=>item.id!==saved.id),saved]);setForm((current:any)=>({...current,location:saved.id}));setLocationOpen(false);setLocationForm({geofence_radius_m:250});setToast('Einsatzort gespeichert und ausgewählt.');}catch(e:any){setToast(e.message);}finally{setBusy(false);}}
  async function save(){
    setBusy(true); let createdId:string|undefined;
    try{
      if(!form.client||!form.location||!form.position||!form.starts_at||!form.ends_at) throw new Error('Bitte alle Pflichtfelder ausfüllen.');
      const start=wallClockMs(form.starts_at), end=wallClockMs(form.ends_at); if(!(end>start)) throw new Error('Das Ende muss nach dem Beginn liegen.');
      const assignedWorkers=Array.isArray(form.workers)?form.workers.filter(Boolean):[]; const requiredCount=Math.max(1,Number(form.required_count||1));
      if(assignedWorkers.length>requiredCount) throw new Error('Mehr Mitarbeiter ausgewählt als benötigte Plätze.');
      const baseStatus=assignedWorkers.length===requiredCount?'draft':form.publish_now?'published':'draft';
      const p:any={client:form.client,location:form.location,position:form.position,starts_at:form.starts_at,ends_at:form.ends_at,break_minutes:automaticBreakMinutes(form.starts_at,form.ends_at),required_count:requiredCount,confirmation_required:!!form.confirmation_required,schedule_groups:form.schedule_groups||[],notes:form.notes||'',status:baseStatus};
      const saved:any=await api(editing?`shifts/${editing}/`:'shifts/',{method:editing?'PATCH':'POST',body:JSON.stringify(p)}); if(!editing) createdId=String(saved.id);
      await api(`shifts/${saved.id}/assign/`,{method:'POST',body:JSON.stringify({workers:assignedWorkers,publish_remaining:!!form.publish_now})}); createdId=undefined; setModal(false); setToast(assignedWorkers.length?`${assignedWorkers.length} Mitarbeiter direkt zugewiesen.`:'Personalbedarf gespeichert.'); await load();
    }catch(e:any){if(createdId){try{await api(`shifts/${createdId}/`,{method:'DELETE'});}catch{} await load();}setToast(e.message);}finally{setBusy(false);}
  }

  async function parseAiOrder(){
    if(!orderText.trim()){setToast('Bitte zuerst den Text der Kundenanfrage einfügen.');return;}
    setBusy(true);
    try{
      const result:any=await api('automation/orders/parse/',{method:'POST',body:JSON.stringify({text:orderText})});
      setParsedOrder(result);setToast(`${result.shifts?.length||0} Schicht(en) erkannt. Bitte kurz prüfen.`);
    }catch(e:any){setToast(e.message);}finally{setBusy(false);}
  }
  async function approveAiOrder(){
    if(!parsedOrder)return void parseAiOrder();
    setBusy(true);
    try{
      const result:any=await api('automation/orders/approve/',{method:'POST',body:JSON.stringify({parsed:parsedOrder,raw_text:orderText})});
      setAiOpen(false);setOrderText('');setParsedOrder(undefined);await load();setToast(`${result.created_count||0} Personalplatz/-plätze als OpenShift erstellt.`);
    }catch(e:any){setToast(e.message);}finally{setBusy(false);}
  }
  async function setConfirmation(item:any,status:'pending'|'confirmed'|'rejected',slotId?:string){setBusy(true);try{await api(`shifts/${item.id}/confirmation/`,{method:'POST',body:JSON.stringify({status,...(slotId?{slot_id:slotId}:{})})});setToast(status==='confirmed'?'Schicht bestätigt.':status==='rejected'?'Schicht abgelehnt.':'Bestätigung erneut angefordert.');await load();}catch(e:any){setToast(e.message);}finally{setBusy(false);}}
  function confirmRelease(){const id=releaseTarget?.id;setReleaseTarget(undefined);if(id) void act(`shifts/${id}/release/`,'Schicht freigegeben.');}
  function navigate(direction:number){if(view==='month')setAnchor(addKeyMonths(anchor,direction));else if(view==='day')setAnchor(addKeyDays(anchor,direction));else setAnchor(addKeyDays(anchor,7*direction));}
  const openItem=(item:any)=>{if(isManager(user))edit(item);};

  const workerView=user.role==='worker'; const clientView=user.role==='client';
  const eyebrow=workerView?'MEINE ARBEIT':clientView?'KUNDENPORTAL':'PERSONALPLANUNG';
  const title=workerView?'Schichten':clientView?'Einsätze':'Personalbedarf & Schichten';
  const intro=workerView?'Freie Einsätze finden und eigene Schichten verwalten.':clientView?'Geplante Einsätze und aktueller Besetzungsstatus für Ihre Aufträge.':'Kundenbedarf erstellen, Mitarbeiter direkt zuweisen oder Restplätze als OpenShift veröffentlichen.';
  const searchPlaceholder=clientView?'Einsatz, Ort oder Position suchen …':'Kunde, Ort oder Position suchen …';
  const rangeTitle=view==='month'?keyLabel(monthStart,{month:'long',year:'numeric'}):view==='day'?keyLabel(anchor,{weekday:'long',day:'2-digit',month:'long',year:'numeric'}):`${keyLabel(weekStart,{day:'2-digit',month:'short'})} – ${keyLabel(addKeyDays(weekStart,6),{day:'2-digit',month:'short',year:'numeric'})}`;

  const renderAkteLink=(kind:AkteKind,id:string|undefined,label:string)=>{
    if(!isManager(user)||!id) return <span>{label}</span>;
    return <a className="sv2-entity-link" href={akteHref(kind,id)} onClick={event=>{event.preventDefault();event.stopPropagation();openAkte(kind,id);}}>{label}</a>;
  };
  const renderWorkerAvatars=(item:any,compact=false)=>{
    const assigned=item.assigned_workers||[];
    if(!assigned.length) return <span className="sv2-no-profile">Noch kein Profilbild</span>;
    const limit=compact?4:8;
    return <div className={`sv2-worker-avatars ${compact?'compact':''}`} aria-label="Profilbilder der zugewiesenen Mitarbeiter">
      {assigned.slice(0,limit).map((worker:any)=>{
        const content=<><span>{workerInitials(worker)}</span>{worker.avatar&&<img src={worker.avatar} alt="" loading="lazy" onError={e=>{e.currentTarget.style.display='none';}}/>}</>;
        return isManager(user)&&worker.id?<a className="sv2-worker-avatar" href={akteHref('worker',worker.id)} key={worker.id||worker.name} title={worker.name} aria-label={`${worker.name} · Akte öffnen`} onClick={event=>{event.preventDefault();event.stopPropagation();openAkte('worker',worker.id);}}>{content}</a>:<span className="sv2-worker-avatar" key={worker.id||worker.name} title={worker.name} aria-label={worker.name}>{content}</span>;
      })}
      {assigned.length>limit&&<span className="sv2-worker-more" title={`${assigned.length-limit} weitere Mitarbeiter`}>+{assigned.length-limit}</span>}
    </div>;
  };
  const renderWorkerNames=(item:any)=>{
    const assigned=item.assigned_workers||[];
    if(!assigned.length) return <span>Noch nicht besetzt</span>;
    return <span className="sv2-worker-names">{assigned.map((worker:any,index:number)=><React.Fragment key={worker.id||worker.name}>{index>0&&<span className="sv2-name-separator">, </span>}{renderAkteLink('worker',worker.id,worker.name||worker.employee_number||'Mitarbeiter')}</React.Fragment>)}</span>;
  };
  const confirmationLabel=(status:string)=>status==='pending'?'Ausstehend':status==='rejected'?'Abgelehnt':'Bestätigt';
  const confirmationColor=(status:string)=>status==='pending'?'warning':status==='rejected'?'danger':'success';
  const renderConfirmationPanel=(item:any,compact=false)=>{
    if(!item.confirmation_required) return null;
    const assigned=item.assigned_workers||[];
    const targets=isManager(user)?assigned:assigned.filter((worker:any)=>worker.is_me);
    if(!targets.length) return <div className="sv2-confirmation-panel"><small>Bestätigung erforderlich · noch keine Zuweisung</small></div>;
    return <div className={`sv2-confirmation-panel ${compact?'compact':''}`} data-testid="shift-confirmations">{targets.map((worker:any)=><div className="sv2-confirmation-row" key={worker.slot_id||worker.id}>
      <span className="sv2-confirmation-person">{isManager(user)?worker.name:'Meine Bestätigung'}</span>
      <IonBadge color={confirmationColor(worker.confirmation_status)}>{confirmationLabel(worker.confirmation_status)}</IonBadge>
      {workerView&&worker.is_me&&worker.confirmation_status==='pending'&&<span className="sv2-confirmation-actions"><IonButton size="small" disabled={busy} onClick={event=>{event.stopPropagation();void setConfirmation(item,'confirmed');}}>Bestätigen</IonButton><IonButton size="small" fill="outline" color="danger" disabled={busy} onClick={event=>{event.stopPropagation();void setConfirmation(item,'rejected');}}>Ablehnen</IonButton></span>}
      {isManager(user)&&!compact&&<span className="sv2-confirmation-actions admin"><IonButton size="small" fill="clear" disabled={busy||worker.confirmation_status==='pending'} onClick={event=>{event.stopPropagation();void setConfirmation(item,'pending',worker.slot_id);}}>Ausstehend</IonButton><IonButton size="small" fill="clear" color="success" disabled={busy||worker.confirmation_status==='confirmed'} onClick={event=>{event.stopPropagation();void setConfirmation(item,'confirmed',worker.slot_id);}}>Bestätigt</IonButton><IonButton size="small" fill="clear" color="danger" disabled={busy||worker.confirmation_status==='rejected'} onClick={event=>{event.stopPropagation();void setConfirmation(item,'rejected',worker.slot_id);}}>Abgelehnt</IonButton></span>}
    </div>)}</div>;
  };
  const renderShiftDetails=(item:any,compact=false)=><div className={`sv2-event-details ${compact?'compact':''}`} data-testid="shift-card-details">
    <div className="sv2-event-line" data-field="client"><IonIcon icon={businessOutline}/><span className="sv2-field-copy"><small>Kunde</small>{renderAkteLink('client',item.client,item.client_name||'Ohne Kunde')}</span></div>
    <div className="sv2-event-line" data-field="location"><IonIcon icon={locationOutline}/><span className="sv2-field-copy"><small>Standort</small><span>{item.location_name||'Ohne Einsatzort'}</span></span></div>
    <div className="sv2-event-line" data-field="workers"><IonIcon icon={peopleOutline}/><span className="sv2-field-copy"><small>Mitarbeiter</small>{renderWorkerNames(item)}</span></div>
    <div className="sv2-event-line" data-field="time"><IonIcon icon={timeOutline}/><span className="sv2-field-copy"><small>Start–Ende</small><span>{tm(item.starts_at)}–{tm(item.ends_at)}</span></span></div>
    <div className="sv2-event-line sv2-profile-line" data-field="profile"><IonIcon icon={personCircleOutline}/><span className="sv2-field-copy"><small>Profilbild</small>{renderWorkerAvatars(item,compact)}</span></div>
    {renderConfirmationPanel(item,compact)}
  </div>;
  const renderMini=(item:any,compact=false)=>{const status=statusInfo(item);const canOpen=isManager(user);const mine=workerView&&tab==='mine';return <article style={clientStyle(item)} className={`sv2-event ${compact?'compact':''}`} key={item.id} role={canOpen?'button':undefined} tabIndex={canOpen?0:undefined} onClick={()=>openItem(item)} onKeyDown={event=>{if(canOpen&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openItem(item);}}}><div className="sv2-event-head"><strong>{item.position_name||'Einsatz'}</strong><span>{status.label}</span></div>{renderShiftDetails(item,compact)}{workerView&&<div className="sv2-mini-actions">{!mine&&status.open&&<IonButton size="small" disabled={busy} onClick={event=>{event.stopPropagation();void act(`shifts/${item.id}/claim/`,'Schicht übernommen.');}}><IonIcon slot="start" icon={checkmarkCircleOutline}/>Übernehmen</IonButton>}{mine&&<IonButton size="small" fill="outline" color="medium" disabled={busy} onClick={event=>{event.stopPropagation();setReleaseTarget(item);}}>Freigeben</IonButton>}</div>}</article>;};

  return <div className="sv2">
    <div className="sv2-title"><div><small>{eyebrow}</small><h1>{title}</h1><p>{intro}</p></div>{isManager(user)&&<div className="button-group"><IonButton data-testid="schedule-create-manual" onClick={create}><IonIcon slot="start" icon={addOutline}/>Manuell</IonButton><IonButton data-testid="schedule-create-ai" fill="outline" onClick={()=>{setParsedOrder(undefined);setOrderText('');setAiOpen(true);}}><IonIcon slot="start" icon={briefcaseOutline}/>AI</IonButton></div>}</div>
    <div className="sv2-search"><IonSearchbar value={search} debounce={350} placeholder={searchPlaceholder} onIonInput={e=>setSearch(String(val(e)))} onIonChange={()=>void load()}/><IonButton fill="outline" onClick={()=>void load()}><IonIcon slot="icon-only" icon={refreshOutline}/></IonButton></div>
    {workerView?<IonSegment scrollable value={tab} onIonChange={e=>setTab(String(val(e)))}><IonSegmentButton value="available"><IonLabel>Verfügbare Schichten</IonLabel></IonSegmentButton><IonSegmentButton value="mine"><IonLabel>Meine Schichten</IonLabel></IonSegmentButton></IonSegment>:isManager(user)?<IonSegment scrollable value={tab} onIonChange={e=>setTab(String(val(e)))}><IonSegmentButton value="open"><IonLabel>Alle Schichten</IonLabel></IonSegmentButton><IonSegmentButton value="filled"><IonLabel>Voll besetzt</IonLabel></IonSegmentButton><IonSegmentButton value="draft"><IonLabel>Entwürfe</IonLabel></IonSegmentButton><IonSegmentButton value="all"><IonLabel>Alle</IonLabel></IonSegmentButton></IonSegment>:null}

    <div className="sv2-wiw-week-strip" data-testid="phase8-week-strip" aria-label="Mobile Wochenwahl">
      <button type="button" className="nav" aria-label="Vorherige Woche" onClick={()=>setAnchor(addKeyDays(anchor,-7))}>‹</button>
      {weekDays.map(key=><button type="button" key={key} className={`${key===anchor?'active ':''}${key===berlinDate()?'today':''}`} onClick={()=>{setAnchor(key);setView('day');}}><span>{keyLabel(key,{weekday:'short'}).slice(0,1)}</span><b>{keyToDate(key).getUTCDate()}</b></button>)}
      <button type="button" className="nav" aria-label="Nächste Woche" onClick={()=>setAnchor(addKeyDays(anchor,7))}>›</button>
    </div>

    <div className="sv2-service-filter" data-testid="schedule-service-filter" role="group" aria-label="Bereich filtern">
      {([['all','Alle'],['service','Service'],['hotel','Hotel'],['housekeeping','Housekeeping']] as [ServiceFilter,string][]).map(([key,label])=><button type="button" key={key} className={serviceFilter===key?'active':''} aria-pressed={serviceFilter===key} data-testid={`schedule-filter-${key}`} onClick={()=>setServiceFilter(key)}>{label}</button>)}
    </div>

    {clientLegend.length>0&&<div className="sv2-client-legend" data-testid="schedule-client-legend" aria-label="Kundenfarben">
      {clientLegend.map(item=><span key={clientKey(item)} style={clientStyle(item)}><i/>{item.client_name||'Ohne Kunde'}</span>)}
    </div>}

    <div className="sv2-view-toolbar" data-testid="schedule-view-toolbar">
      <div className="sv2-view-switch" role="group" aria-label="Planungsansicht">
        {([['list','Liste'],['day','Tag'],['week','Woche'],['month','Monat'],['timeline','Einsatzorte']] as [ScheduleView,string][]).map(([key,label])=><button type="button" key={key} data-testid={`schedule-view-${key}`} aria-pressed={view===key} className={view===key?'active':''} onClick={()=>setView(key)}>{label}</button>)}
      </div>
      {view!=='list'&&<div className="sv2-date-nav"><button type="button" aria-label="Vorheriger Zeitraum" onClick={()=>navigate(-1)}>‹</button><button type="button" className="sv2-range-title" onClick={()=>setAnchor(berlinDate())}>{rangeTitle}</button><button type="button" aria-label="Nächster Zeitraum" onClick={()=>navigate(1)}>›</button><button type="button" className="today" onClick={()=>setAnchor(berlinDate())}>Heute</button></div>}
    </div>

    {view==='list'&&<div className="sv2-list">{visible.map((x:any)=>{const mine=workerView&&tab==='mine';const status=statusInfo(x);const assigned=x.assigned_workers||[];return <article style={clientStyle(x)} className={`sv2-card ${mine?'mine':''}`} key={x.id}>
      <div className="sv2-date"><b>{berlinDay(x.starts_at)}</b><span>{berlinMonth(x.starts_at)}</span></div>
      <div className="sv2-body"><div className="sv2-list-head"><h3>{x.position_name||'Einsatz'}</h3><span>{x.break_minutes||0} Min. Pause</span></div>{renderShiftDetails(x)}<div className="sv2-meter"><span style={{width:`${Math.min(100,(Number(x.filled_count||0)/Number(x.required_count||1))*100)}%`}}/></div><em>{x.filled_count||0}/{x.required_count||1} besetzt · {x.open_count||0} frei</em></div>
      <div className="sv2-side"><IonBadge color={status.color}>{status.label}</IonBadge>{workerView&&!mine&&status.open&&<IonButton disabled={busy} onClick={()=>void act(`shifts/${x.id}/claim/`,'Schicht übernommen.')}><IonIcon slot="start" icon={checkmarkCircleOutline}/>Übernehmen</IonButton>}{workerView&&mine&&<IonButton fill="outline" color="medium" disabled={busy} onClick={()=>setReleaseTarget(x)}>Freigeben</IonButton>}{isManager(user)&&x.status==='draft'&&Number(x.open_count||0)>0&&<IonButton size="small" onClick={()=>void act(`shifts/${x.id}/publish/`,'OpenShift veröffentlicht.')}>Veröffentlichen</IonButton>}{isManager(user)&&<IonButton size="small" fill="clear" onClick={()=>edit(x)}>Bearbeiten</IonButton>}</div>
    </article>})}{!visible.length&&<div className="sv2-empty"><h3>Keine passenden Einsätze</h3><p>Suche oder Filter ändern.</p></div>}</div>}

    {view==='day'&&<div className="sv2-day-wrap" data-testid="schedule-day-view"><div className="sv2-single-day"><header><div><small>{keyLabel(anchor,{weekday:'long'})}</small><h2>{keyLabel(anchor,{day:'2-digit',month:'long',year:'numeric'})}</h2></div><span>{(rowsByDay[anchor]||[]).length} Einsätze</span></header><div className="sv2-single-day-events">{(rowsByDay[anchor]||[]).map(item=>renderMini(item))}{!(rowsByDay[anchor]||[]).length&&<div className="sv2-no-events">Keine Einsätze an diesem Tag.</div>}</div></div></div>}

    {view==='week'&&<div className="sv2-week-wrap" data-testid="schedule-week-view"><div className="sv2-week-grid">{weekDays.map(key=><section className={`sv2-week-day ${key===berlinDate()?'is-today':''}`} key={key}><header><b>{keyLabel(key,{weekday:'short'})}</b><span>{keyLabel(key,{day:'2-digit',month:'2-digit'})}</span></header><div className="sv2-day-events">{(rowsByDay[key]||[]).map(item=>renderMini(item))}{!(rowsByDay[key]||[]).length&&<small className="sv2-no-events">Keine Einsätze</small>}</div></section>)}</div></div>}

    {view==='month'&&<div className="sv2-month-wrap" data-testid="schedule-month-view"><div className="sv2-month-weekdays">{['Mo','Di','Mi','Do','Fr','Sa','So'].map(day=><b key={day}>{day}</b>)}</div><div className="sv2-month-grid">{monthDays.map(key=>{const inMonth=key.slice(0,7)===monthStart.slice(0,7);return <section className={`sv2-month-day ${!inMonth?'outside':''} ${key===berlinDate()?'is-today':''}`} key={key}><header>{keyToDate(key).getUTCDate()}</header><div>{(rowsByDay[key]||[]).slice(0,4).map(item=>renderMini(item,true))}{(rowsByDay[key]||[]).length>4&&<small className="sv2-more">+{(rowsByDay[key]||[]).length-4} weitere</small>}</div></section>;})}</div></div>}

    {view==='timeline'&&<div className="sv2-timeline-wrap" data-testid="schedule-timeline-view"><div className="sv2-timeline-grid"><div className="sv2-timeline-corner">Einsatzort</div>{weekDays.map(key=><div className={`sv2-timeline-head ${key===berlinDate()?'is-today':''}`} key={key}><b>{keyLabel(key,{weekday:'short'})}</b><span>{keyLabel(key,{day:'2-digit',month:'2-digit'})}</span></div>)}{timelineLocations.map(location=><React.Fragment key={location}><div className="sv2-location-label"><IonIcon icon={locationOutline}/><b>{location}</b></div>{weekDays.map(key=><div className="sv2-timeline-cell" key={`${location}-${key}`}>{visible.filter(item=>(item.location_name||'Ohne Einsatzort')===location&&shiftDateKey(item.starts_at)===key).map(item=>renderMini(item,true))}</div>)}</React.Fragment>)}</div>{!timelineLocations.length&&<div className="sv2-empty"><h3>Keine Einsätze in dieser Woche</h3><p>Zeitraum wechseln oder Filter ändern.</p></div>}</div>}

    <div className="sv2-wiw-total" data-testid="phase8-week-total"><span>Gesamtstunden</span><strong>{weekTotalHours.toFixed(1)}</strong></div>
    {isManager(user)&&<button type="button" className="sv2-wiw-fab" aria-label="Schicht anlegen" onClick={create}>+</button>}

    <IonModal isOpen={modal} onDidDismiss={()=>setModal(false)}><div className="sv2-modal"><div className="sv2-modal-head"><h2>{editing?'Personalbedarf bearbeiten':'Personalbedarf anlegen'}</h2><IonButton fill="clear" onClick={()=>setModal(false)}>Schließen</IonButton></div><div className="sv2-form">
      <IonSelect fill="outline" label="Kunde *" labelPlacement="floating" value={form.client} onIonChange={e=>{const id=val(e);const selected=clients.find(x=>x.id===id);const groups=scheduleGroupsForClient(selected?.name);setForm({...form,client:id,location:undefined,schedule_groups:groups.length?groups:form.schedule_groups||[]});}}>{clients.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <div className="sv2-location-field"><IonSelect fill="outline" label="Einsatzort *" labelPlacement="floating" value={form.location} disabled={!form.client} onIonChange={e=>setForm({...form,location:val(e)})}>{locations.filter(x=>form.client&&x.client===form.client).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect><IonButton fill="outline" disabled={!form.client} onClick={()=>setLocationOpen(true)}><IonIcon slot="start" icon={addOutline}/>Neu</IonButton></div>
      <IonSelect fill="outline" label="Position *" labelPlacement="floating" value={form.position} onIonChange={e=>{const id=val(e);const position=positions.find(x=>x.id===id);const client=clients.find(x=>x.id===form.client);const clientGroups=scheduleGroupsForClient(client?.name);setForm({...form,position:id,schedule_groups:clientGroups.length?clientGroups:scheduleGroupsForPosition(position?.name)});}}>{positions.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <FriendlyDateTime label="Beginn" value={form.starts_at} onChange={next=>setShiftDateTime('starts_at',next)}/><FriendlyDateTime label="Ende" value={form.ends_at} onChange={next=>setShiftDateTime('ends_at',next)}/>
      <div className="sv2-staff-stepper" data-testid="required-count-stepper"><span>Benötigte Mitarbeiter *</span><div><button type="button" aria-label="Mitarbeiter reduzieren" disabled={Number(form.required_count||1)<=Math.max(1,(form.workers||[]).length)} onClick={()=>setForm({...form,required_count:Math.max((form.workers||[]).length,Number(form.required_count||1)-1,1)})}>−</button><strong>{form.required_count||1}</strong><button type="button" aria-label="Mitarbeiter erhöhen" onClick={()=>setForm({...form,required_count:Number(form.required_count||1)+1})}>+</button></div></div><div className="sv2-auto-break"><span>Pause automatisch</span><strong>{automaticBreakMinutes(form.starts_at,form.ends_at)} Min.</strong><small>&lt; 6h: 0 · ab 6h: 30 · ab 9h: 45 · ab 11h: 60</small></div>
      <IonSelect className="full" multiple interface="alert" fill="outline" label="Mitarbeiter direkt zuweisen (optional)" labelPlacement="floating" value={form.workers||[]} onIonChange={e=>{const selected=Array.isArray(val(e))?val(e):[];const limit=Math.max(1,Number(form.required_count||1));if(selected.length>limit)setToast(`Maximal ${limit} Mitarbeiter auswählbar.`);setForm({...form,workers:selected.slice(0,limit)});}}>{workers.map(worker=><IonSelectOption key={worker.id} value={worker.id}>{workerLabel(worker)} · {worker.employee_number}</IonSelectOption>)}</IonSelect>
      {(form.workers||[]).length>0&&<div className="full sv2-assignment-note">{(form.workers||[]).length} von {form.required_count||1} Plätzen werden direkt zugewiesen. Freie Restplätze können als OpenShift veröffentlicht werden.</div>}
      <IonSelect className="full" multiple interface="alert" fill="outline" label="Zeitplan · Sichtbare Mitarbeitergruppen" labelPlacement="floating" value={form.schedule_groups||[]} onIonChange={e=>setForm({...form,schedule_groups:Array.isArray(val(e))?val(e):[]})}>{SCHEDULE_GROUPS.map(([key,label])=><IonSelectOption key={key} value={key}>{label}</IonSelectOption>)}</IonSelect>
      <IonSelect className="full" fill="outline" label="Textvorlage für Mitarbeiterhinweis" labelPlacement="floating" value="" onIonChange={e=>{const key=String(val(e)||'');const template=NOTE_TEMPLATES.find(([id])=>id===key)?.[1];if(key&&template)setForm({...form,notes:template});}}>{NOTE_TEMPLATES.map(([key,label])=><IonSelectOption key={key||'empty'} value={key}>{label}</IonSelectOption>)}</IonSelect>
      <IonTextarea className="full" fill="outline" label="Hinweise für Mitarbeiter" labelPlacement="floating" value={form.notes} onIonInput={e=>setForm({...form,notes:val(e)})}/><label className="sv2-toggle full">Bestätigung durch zugewiesene Mitarbeiter erforderlich <IonToggle checked={!!form.confirmation_required} onIonChange={e=>setForm({...form,confirmation_required:e.detail.checked})}/></label><label className="sv2-toggle full">{(form.workers||[]).length>0?'Restliche freie Plätze als OpenShift veröffentlichen':'Direkt als OpenShift veröffentlichen'} <IonToggle checked={!!form.publish_now} onIonChange={e=>setForm({...form,publish_now:e.detail.checked})}/></label>
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setModal(false)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>void save()}>Speichern</IonButton></div></div></IonModal>

    <IonModal isOpen={locationOpen} onDidDismiss={()=>setLocationOpen(false)}><div className="sv2-modal"><div className="sv2-modal-head"><h2>Einsatzort anlegen</h2><IonButton fill="clear" onClick={()=>setLocationOpen(false)}>Schließen</IonButton></div><div className="sv2-form"><IonInput fill="outline" label="Bezeichnung *" labelPlacement="floating" value={locationForm.name} onIonInput={e=>setLocationForm({...locationForm,name:val(e)})}/><IonTextarea className="full" fill="outline" label="Adresse *" labelPlacement="floating" value={locationForm.address} onIonInput={e=>setLocationForm({...locationForm,address:val(e)})}/><IonInput fill="outline" type="number" label="Geofence-Radius in Metern" labelPlacement="floating" value={locationForm.geofence_radius_m} onIonInput={e=>setLocationForm({...locationForm,geofence_radius_m:val(e)})}/></div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setLocationOpen(false)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>void saveInlineLocation()}>Speichern</IonButton></div></div></IonModal>

    <IonModal isOpen={aiOpen} onDidDismiss={()=>{setAiOpen(false);setParsedOrder(undefined);}}><div className="sv2-modal" data-testid="schedule-ai-intake"><div className="sv2-modal-head"><div><small>DIENSTPLAN · AI</small><h2>Personalbedarf mit AI erfassen</h2></div><IonButton fill="clear" onClick={()=>setAiOpen(false)}>Schließen</IonButton></div><div className="sv2-form">
      <IonTextarea className="full" autoGrow fill="outline" label="Text aus Kunden-E-Mail / Anfrage" labelPlacement="floating" value={orderText} onIonInput={e=>{setOrderText(String(val(e)));setParsedOrder(undefined);}}/>
      {parsedOrder&&<div className="full sv2-assignment-note"><b>{parsedOrder.request_id||'Anfrage erkannt'}</b><p>Bitte die erkannten Schichten kurz prüfen:</p>{parsedOrder.shifts?.map((item:any,index:number)=><div key={index}>{item.date} · {item.start_time}–{item.end_time} · {item.count}× {item.role} · {item.site_text||item.location_text}</div>)}</div>}
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setAiOpen(false)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>void(parsedOrder?approveAiOrder():parseAiOrder())}>{parsedOrder?'Prüfen & OpenShifts erstellen':'Mit AI analysieren'}</IonButton></div></div></IonModal>
    <IonAlert isOpen={!!releaseTarget} onDidDismiss={()=>setReleaseTarget(undefined)} header="Schicht freigeben?" message={releaseTarget?`${releaseTarget.position_name || 'Diese Schicht'} wird wieder für andere Mitarbeiter verfügbar.`:''} buttons={[{text:'Abbrechen',role:'cancel'},{text:'Freigeben',role:'destructive',handler:confirmRelease}]}/>
    <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={()=>setToast('')}/>
  </div>;
}
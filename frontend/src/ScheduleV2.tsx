import React, { useEffect, useMemo, useState } from 'react';
import { IonAlert, IonBadge, IonButton, IonIcon, IonInput, IonLabel, IonModal, IonSearchbar, IonSegment, IonSegmentButton, IonSelect, IonSelectOption, IonTextarea, IonToast, IonToggle } from '@ionic/react';
import { addOutline, checkmarkCircleOutline, locationOutline, refreshOutline, timeOutline } from 'ionicons/icons';
import { api, User } from './api';
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

function FriendlyDateTime({label,value,onChange}:{label:string;value?:string;onChange:(next:string)=>void}) {
  const parts=splitDateTime(value);
  const setDate=(date:string)=>onChange(joinDateTime(date,parts.time||'09:00'));
  const setTime=(time:string)=>onChange(joinDateTime(parts.date||berlinDate(),time));
  return <div className="sv2-datetime" data-testid={`datetime-${label.toLowerCase()}`}>
    <div className="sv2-datetime-head"><b>{label} *</b><div className="sv2-date-shortcuts"><IonButton size="small" fill="clear" onClick={()=>setDate(berlinDate())}>Heute</IonButton><IonButton size="small" fill="clear" onClick={()=>setDate(berlinDate(1))}>Morgen</IonButton></div></div>
    <div className="sv2-datetime-fields"><IonInput aria-label={`${label} Datum`} fill="outline" type="date" label="Datum" labelPlacement="floating" value={parts.date} onIonInput={e=>setDate(String(val(e)))}/><IonInput aria-label={`${label} Uhrzeit`} fill="outline" type="time" step="900" label="Uhrzeit" labelPlacement="floating" value={parts.time} onIonInput={e=>setTime(String(val(e)))}/></div>
  </div>;
}

export default function ScheduleV2({user}:{user:User}) {
  const [rows,setRows]=useState<any[]>([]), [clients,setClients]=useState<any[]>([]), [locations,setLocations]=useState<any[]>([]), [positions,setPositions]=useState<any[]>([]), [orders,setOrders]=useState<any[]>([]), [workers,setWorkers]=useState<any[]>([]);
  const [tab,setTab]=useState(user.role==='worker'?'available':'open'), [search,setSearch]=useState(''), [modal,setModal]=useState(false), [editing,setEditing]=useState<string>(), [busy,setBusy]=useState(false), [toast,setToast]=useState('');
  const [form,setForm]=useState<any>({required_count:1,break_minutes:0,publish_now:true,workers:[]});
  const [releaseTarget,setReleaseTarget]=useState<any>();
  const [view,setView]=useState<ScheduleView>('list');
  const [anchor,setAnchor]=useState(berlinDate());
  const [serviceFilter,setServiceFilter]=useState<ServiceFilter>('all');

  async function load() {
    const q=search.trim()?`&search=${encodeURIComponent(search.trim())}`:'';
    if(user.role==='worker') { const endpoint=tab==='mine'?'shifts/mine/':'shifts/available/'; setRows(unpack(await api(`${endpoint}?ordering=starts_at${q}`))); return; }
    if(user.role==='client') { setRows(unpack(await api(`shifts/?ordering=starts_at${q}`))); return; }
    const [s,c,l,p,o,w]=await Promise.all([api(`shifts/?ordering=starts_at${q}`),api('clients/'),api('locations/'),api('positions/'),api('orders/'),api('workers/?ordering=user__last_name')]);
    setRows(unpack(s)); setClients(unpack(c)); setLocations(unpack(l)); setPositions(unpack(p)); setOrders(unpack(o)); setWorkers(unpack(w).filter((item:any)=>item.active!==false&&!isSyntheticWorker(item)));
  }
  useEffect(()=>{void load();},[tab]);

  const clientHueMap=useMemo(()=>{
    const keys=Array.from(new Set(rows.map(clientKey))).sort();
    return new Map(keys.map((key,index)=>[key,(18+index*137.508)%360]));
  },[rows]);
  const clientStyle=(item:any)=>({'--sv2-client-hue':String(clientHueMap.get(clientKey(item))??215)} as React.CSSProperties);

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

  async function act(path:string,msg:string){setBusy(true);try{await api(path,{method:'POST',body:'{}'});setToast(msg);await load();}catch(e:any){setToast(e.message);}finally{setBusy(false);}}
  function create(){setEditing(undefined);setForm({required_count:1,break_minutes:0,publish_now:true,workers:[]});setModal(true);}
  function edit(x:any){setEditing(x.id);setForm({...x,workers:(x.assigned_workers||[]).map((worker:any)=>worker.id),starts_at:x.starts_at?.slice(0,16),ends_at:x.ends_at?.slice(0,16),publish_now:x.status==='published'});setModal(true);}
  function setShiftDateTime(field:'starts_at'|'ends_at',next:string){setForm((current:any)=>{const updated={...current,[field]:next};if(field==='starts_at'&&next){const start=wallClockMs(next);const currentEnd=current.ends_at?wallClockMs(current.ends_at):undefined;if(!currentEnd||currentEnd<=start)updated.ends_at=fromWallClockMs(start+4*60*60*1000);}return updated;});}
  async function save(){
    setBusy(true); let createdId:string|undefined;
    try{
      if(!form.client||!form.location||!form.position||!form.starts_at||!form.ends_at) throw new Error('Bitte alle Pflichtfelder ausfüllen.');
      const start=wallClockMs(form.starts_at), end=wallClockMs(form.ends_at); if(!(end>start)) throw new Error('Das Ende muss nach dem Beginn liegen.');
      const assignedWorkers=Array.isArray(form.workers)?form.workers.filter(Boolean):[]; const requiredCount=Math.max(1,Number(form.required_count||1));
      if(assignedWorkers.length>requiredCount) throw new Error('Mehr Mitarbeiter ausgewählt als benötigte Plätze.');
      const baseStatus=assignedWorkers.length===requiredCount?'draft':form.publish_now?'published':'draft';
      const p:any={client:form.client,location:form.location,position:form.position,order:form.order||null,starts_at:form.starts_at,ends_at:form.ends_at,break_minutes:Number(form.break_minutes||0),required_count:requiredCount,notes:form.notes||'',status:baseStatus};
      const saved:any=await api(editing?`shifts/${editing}/`:'shifts/',{method:editing?'PATCH':'POST',body:JSON.stringify(p)}); if(!editing) createdId=String(saved.id);
      await api(`shifts/${saved.id}/assign/`,{method:'POST',body:JSON.stringify({workers:assignedWorkers,publish_remaining:!!form.publish_now})}); createdId=undefined; setModal(false); setToast(assignedWorkers.length?`${assignedWorkers.length} Mitarbeiter direkt zugewiesen.`:'Personalbedarf gespeichert.'); await load();
    }catch(e:any){if(createdId){try{await api(`shifts/${createdId}/`,{method:'DELETE'});}catch{} await load();}setToast(e.message);}finally{setBusy(false);}
  }
  function confirmRelease(){const id=releaseTarget?.id;setReleaseTarget(undefined);if(id) void act(`shifts/${id}/release/`,'Schicht freigegeben.');}
  function navigate(direction:number){if(view==='month')setAnchor(addKeyMonths(anchor,direction));else if(view==='day')setAnchor(addKeyDays(anchor,direction));else setAnchor(addKeyDays(anchor,7*direction));}
  const openItem=(item:any)=>{if(isManager(user))edit(item);};

  const workerView=user.role==='worker'; const clientView=user.role==='client';
  const eyebrow=workerView?'MEINE ARBEIT':clientView?'KUNDENPORTAL':'PERSONALPLANUNG';
  const title=workerView?'Schichten':clientView?'Einsätze':'Personalbedarf & Schichten';
  const intro=workerView?'Freie Einsätze finden und eigene Schichten verwalten.':clientView?'Geplante Einsätze und aktueller Besetzungsstatus für Ihre Aufträge.':'Kundenbedarf erstellen, Mitarbeiter direkt zuweisen oder Restplätze als OpenShift veröffentlichen.';
  const searchPlaceholder=clientView?'Einsatz, Ort oder Position suchen …':'Kunde, Ort, Position oder Auftrag suchen …';
  const rangeTitle=view==='month'?keyLabel(monthStart,{month:'long',year:'numeric'}):view==='day'?keyLabel(anchor,{weekday:'long',day:'2-digit',month:'long',year:'numeric'}):`${keyLabel(weekStart,{day:'2-digit',month:'short'})} – ${keyLabel(addKeyDays(weekStart,6),{day:'2-digit',month:'short',year:'numeric'})}`;

  const renderWorkerAvatars=(item:any,compact=false)=>{
    const assigned=item.assigned_workers||[];
    if(!assigned.length) return null;
    const limit=compact?4:8;
    return <div className={`sv2-worker-avatars ${compact?'compact':''}`} aria-label="Zugewiesene Mitarbeiter">
      {assigned.slice(0,limit).map((worker:any)=><span className="sv2-worker-avatar" key={worker.id||worker.name} title={worker.name} aria-label={worker.name}>
        <span>{workerInitials(worker)}</span>{worker.avatar&&<img src={worker.avatar} alt="" loading="lazy" onError={e=>{e.currentTarget.style.display='none';}}/>}
      </span>)}
      {assigned.length>limit&&<span className="sv2-worker-more" title={`${assigned.length-limit} weitere Mitarbeiter`}>+{assigned.length-limit}</span>}
    </div>;
  };
  const renderClientLabel=(item:any)=><span className="sv2-client-label"><i/>{item.client_name||'Ohne Kunde'}</span>;
  const renderMini=(item:any,compact=false)=>{const status=statusInfo(item);return <button type="button" style={clientStyle(item)} className={`sv2-event ${compact?'compact':''}`} key={item.id} onClick={()=>openItem(item)}><span className={`sv2-event-dot ${status.label.toLowerCase()}`}/><b>{tm(item.starts_at)} {item.position_name}</b><small>{renderClientLabel(item)} <span>· {item.filled_count||0}/{item.required_count||1}</span></small>{renderWorkerAvatars(item,compact)}</button>;};

  return <div className="sv2">
    <div className="sv2-title"><div><small>{eyebrow}</small><h1>{title}</h1><p>{intro}</p></div>{isManager(user)&&<IonButton onClick={create}><IonIcon slot="start" icon={addOutline}/>Personalbedarf</IonButton>}</div>
    <div className="sv2-search"><IonSearchbar value={search} debounce={350} placeholder={searchPlaceholder} onIonInput={e=>setSearch(String(val(e)))} onIonChange={()=>void load()}/><IonButton fill="outline" onClick={()=>void load()}><IonIcon slot="icon-only" icon={refreshOutline}/></IonButton></div>
    {workerView?<IonSegment scrollable value={tab} onIonChange={e=>setTab(String(val(e)))}><IonSegmentButton value="available"><IonLabel>Verfügbare Schichten</IonLabel></IonSegmentButton><IonSegmentButton value="mine"><IonLabel>Meine Schichten</IonLabel></IonSegmentButton></IonSegment>:isManager(user)?<IonSegment scrollable value={tab} onIonChange={e=>setTab(String(val(e)))}><IonSegmentButton value="open"><IonLabel>Offen</IonLabel></IonSegmentButton><IonSegmentButton value="filled"><IonLabel>Voll besetzt</IonLabel></IonSegmentButton><IonSegmentButton value="draft"><IonLabel>Entwürfe</IonLabel></IonSegmentButton><IonSegmentButton value="all"><IonLabel>Alle</IonLabel></IonSegmentButton></IonSegment>:null}

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
      <div className="sv2-body"><small>{renderClientLabel(x)}</small><h3>{x.position_name}</h3><p><IonIcon icon={timeOutline}/> {tm(x.starts_at)}–{tm(x.ends_at)} · {x.break_minutes||0} Min.</p><p><IonIcon icon={locationOutline}/> {x.location_name}</p>{assigned.length>0&&<div className="sv2-list-assignees"><b>Zugewiesen</b>{renderWorkerAvatars(x)}</div>}<div className="sv2-meter"><span style={{width:`${Math.min(100,(Number(x.filled_count||0)/Number(x.required_count||1))*100)}%`}}/></div><em>{x.filled_count||0}/{x.required_count||1} besetzt · {x.open_count||0} frei</em></div>
      <div className="sv2-side"><IonBadge color={status.color}>{status.label}</IonBadge>{workerView&&!mine&&status.open&&<IonButton disabled={busy} onClick={()=>void act(`shifts/${x.id}/claim/`,'Schicht übernommen.')}><IonIcon slot="start" icon={checkmarkCircleOutline}/>Übernehmen</IonButton>}{workerView&&mine&&<IonButton fill="outline" color="medium" disabled={busy} onClick={()=>setReleaseTarget(x)}>Freigeben</IonButton>}{isManager(user)&&x.status==='draft'&&Number(x.open_count||0)>0&&<IonButton size="small" onClick={()=>void act(`shifts/${x.id}/publish/`,'OpenShift veröffentlicht.')}>Veröffentlichen</IonButton>}{isManager(user)&&<IonButton size="small" fill="clear" onClick={()=>edit(x)}>Bearbeiten</IonButton>}</div>
    </article>})}{!visible.length&&<div className="sv2-empty"><h3>Keine passenden Einsätze</h3><p>Suche oder Filter ändern.</p></div>}</div>}

    {view==='day'&&<div className="sv2-day-wrap" data-testid="schedule-day-view"><div className="sv2-single-day"><header><div><small>{keyLabel(anchor,{weekday:'long'})}</small><h2>{keyLabel(anchor,{day:'2-digit',month:'long',year:'numeric'})}</h2></div><span>{(rowsByDay[anchor]||[]).length} Einsätze</span></header><div className="sv2-single-day-events">{(rowsByDay[anchor]||[]).map(item=>renderMini(item))}{!(rowsByDay[anchor]||[]).length&&<div className="sv2-no-events">Keine Einsätze an diesem Tag.</div>}</div></div></div>}

    {view==='week'&&<div className="sv2-week-wrap" data-testid="schedule-week-view"><div className="sv2-week-grid">{weekDays.map(key=><section className={`sv2-week-day ${key===berlinDate()?'is-today':''}`} key={key}><header><b>{keyLabel(key,{weekday:'short'})}</b><span>{keyLabel(key,{day:'2-digit',month:'2-digit'})}</span></header><div className="sv2-day-events">{(rowsByDay[key]||[]).map(item=>renderMini(item))}{!(rowsByDay[key]||[]).length&&<small className="sv2-no-events">Keine Einsätze</small>}</div></section>)}</div></div>}

    {view==='month'&&<div className="sv2-month-wrap" data-testid="schedule-month-view"><div className="sv2-month-weekdays">{['Mo','Di','Mi','Do','Fr','Sa','So'].map(day=><b key={day}>{day}</b>)}</div><div className="sv2-month-grid">{monthDays.map(key=>{const inMonth=key.slice(0,7)===monthStart.slice(0,7);return <section className={`sv2-month-day ${!inMonth?'outside':''} ${key===berlinDate()?'is-today':''}`} key={key}><header>{keyToDate(key).getUTCDate()}</header><div>{(rowsByDay[key]||[]).slice(0,4).map(item=>renderMini(item,true))}{(rowsByDay[key]||[]).length>4&&<small className="sv2-more">+{(rowsByDay[key]||[]).length-4} weitere</small>}</div></section>;})}</div></div>}

    {view==='timeline'&&<div className="sv2-timeline-wrap" data-testid="schedule-timeline-view"><div className="sv2-timeline-grid"><div className="sv2-timeline-corner">Einsatzort</div>{weekDays.map(key=><div className={`sv2-timeline-head ${key===berlinDate()?'is-today':''}`} key={key}><b>{keyLabel(key,{weekday:'short'})}</b><span>{keyLabel(key,{day:'2-digit',month:'2-digit'})}</span></div>)}{timelineLocations.map(location=><React.Fragment key={location}><div className="sv2-location-label"><IonIcon icon={locationOutline}/><b>{location}</b></div>{weekDays.map(key=><div className="sv2-timeline-cell" key={`${location}-${key}`}>{visible.filter(item=>(item.location_name||'Ohne Einsatzort')===location&&shiftDateKey(item.starts_at)===key).map(item=>renderMini(item,true))}</div>)}</React.Fragment>)}</div>{!timelineLocations.length&&<div className="sv2-empty"><h3>Keine Einsätze in dieser Woche</h3><p>Zeitraum wechseln oder Filter ändern.</p></div>}</div>}

    <IonModal isOpen={modal} onDidDismiss={()=>setModal(false)}><div className="sv2-modal"><div className="sv2-modal-head"><h2>{editing?'Personalbedarf bearbeiten':'Personalbedarf anlegen'}</h2><IonButton fill="clear" onClick={()=>setModal(false)}>Schließen</IonButton></div><div className="sv2-form">
      <IonSelect fill="outline" label="Kunde *" labelPlacement="floating" value={form.client} onIonChange={e=>setForm({...form,client:val(e)})}>{clients.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <IonSelect fill="outline" label="Auftrag" labelPlacement="floating" value={form.order} onIonChange={e=>setForm({...form,order:val(e)})}><IonSelectOption value="">Ohne Auftrag</IonSelectOption>{orders.filter(x=>!form.client||x.client===form.client).map(x=><IonSelectOption key={x.id} value={x.id}>{x.title}</IonSelectOption>)}</IonSelect>
      <IonSelect fill="outline" label="Einsatzort *" labelPlacement="floating" value={form.location} onIonChange={e=>setForm({...form,location:val(e)})}>{locations.filter(x=>!form.client||!x.client||x.client===form.client).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <IonSelect fill="outline" label="Position *" labelPlacement="floating" value={form.position} onIonChange={e=>setForm({...form,position:val(e)})}>{positions.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <FriendlyDateTime label="Beginn" value={form.starts_at} onChange={next=>setShiftDateTime('starts_at',next)}/><FriendlyDateTime label="Ende" value={form.ends_at} onChange={next=>setShiftDateTime('ends_at',next)}/>
      <IonInput fill="outline" type="number" min="1" label="Benötigte Mitarbeiter *" labelPlacement="floating" value={form.required_count} onIonInput={e=>setForm({...form,required_count:Math.max(Number(val(e)||1),(form.workers||[]).length)})}/><IonInput fill="outline" type="number" min="0" label="Pause (Min.)" labelPlacement="floating" value={form.break_minutes} onIonInput={e=>setForm({...form,break_minutes:val(e)})}/>
      <IonSelect className="full" multiple interface="alert" fill="outline" label="Mitarbeiter direkt zuweisen (optional)" labelPlacement="floating" value={form.workers||[]} onIonChange={e=>{const selected=Array.isArray(val(e))?val(e):[];setForm({...form,workers:selected,required_count:Math.max(Number(form.required_count||1),selected.length)});}}>{workers.map(worker=><IonSelectOption key={worker.id} value={worker.id}>{workerLabel(worker)} · {worker.employee_number}</IonSelectOption>)}</IonSelect>
      {(form.workers||[]).length>0&&<div className="full sv2-assignment-note">{(form.workers||[]).length} von {form.required_count||1} Plätzen werden direkt zugewiesen. Freie Restplätze können als OpenShift veröffentlicht werden.</div>}
      <IonTextarea className="full" fill="outline" label="Hinweise für Mitarbeiter" labelPlacement="floating" value={form.notes} onIonInput={e=>setForm({...form,notes:val(e)})}/><label className="sv2-toggle full">{(form.workers||[]).length>0?'Restliche freie Plätze als OpenShift veröffentlichen':'Direkt als OpenShift veröffentlichen'} <IonToggle checked={!!form.publish_now} onIonChange={e=>setForm({...form,publish_now:e.detail.checked})}/></label>
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setModal(false)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>void save()}>Speichern</IonButton></div></div></IonModal>
    <IonAlert isOpen={!!releaseTarget} onDidDismiss={()=>setReleaseTarget(undefined)} header="Schicht freigeben?" message={releaseTarget?`${releaseTarget.position_name || 'Diese Schicht'} wird wieder für andere Mitarbeiter verfügbar.`:''} buttons={[{text:'Abbrechen',role:'cancel'},{text:'Freigeben',role:'destructive',handler:confirmRelease}]}/>
    <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={()=>setToast('')}/>
  </div>;
}

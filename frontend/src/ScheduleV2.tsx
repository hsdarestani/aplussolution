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

function FriendlyDateTime({label,value,onChange}:{label:string;value?:string;onChange:(next:string)=>void}) {
  const parts=splitDateTime(value);
  const setDate=(date:string)=>onChange(joinDateTime(date,parts.time||'09:00'));
  const setTime=(time:string)=>onChange(joinDateTime(parts.date||berlinDate(),time));
  return <div className="sv2-datetime" data-testid={`datetime-${label.toLowerCase()}`}>
    <div className="sv2-datetime-head">
      <b>{label} *</b>
      <div className="sv2-date-shortcuts">
        <IonButton size="small" fill="clear" onClick={()=>setDate(berlinDate())}>Heute</IonButton>
        <IonButton size="small" fill="clear" onClick={()=>setDate(berlinDate(1))}>Morgen</IonButton>
      </div>
    </div>
    <div className="sv2-datetime-fields">
      <IonInput aria-label={`${label} Datum`} fill="outline" type="date" label="Datum" labelPlacement="floating" value={parts.date} onIonInput={e=>setDate(String(val(e)))}/>
      <IonInput aria-label={`${label} Uhrzeit`} fill="outline" type="time" step="900" label="Uhrzeit" labelPlacement="floating" value={parts.time} onIonInput={e=>setTime(String(val(e)))}/>
    </div>
  </div>;
}

export default function ScheduleV2({user}:{user:User}) {
  const [rows,setRows]=useState<any[]>([]), [clients,setClients]=useState<any[]>([]), [locations,setLocations]=useState<any[]>([]), [positions,setPositions]=useState<any[]>([]), [orders,setOrders]=useState<any[]>([]), [workers,setWorkers]=useState<any[]>([]);
  const [tab,setTab]=useState(user.role==='worker'?'available':'open'), [search,setSearch]=useState(''), [modal,setModal]=useState(false), [editing,setEditing]=useState<string>(), [busy,setBusy]=useState(false), [toast,setToast]=useState('');
  const [form,setForm]=useState<any>({required_count:1,break_minutes:0,publish_now:true,workers:[]});
  const [releaseTarget,setReleaseTarget]=useState<any>();

  async function load() {
    const q=search.trim()?`&search=${encodeURIComponent(search.trim())}`:'';
    if(user.role==='worker') {
      const endpoint=tab==='mine'?'shifts/mine/':'shifts/available/';
      setRows(unpack(await api(`${endpoint}?ordering=starts_at${q}`))); return;
    }
    if(user.role==='client') {
      setRows(unpack(await api(`shifts/?ordering=starts_at${q}`)));
      return;
    }
    const [s,c,l,p,o,w]=await Promise.all([api(`shifts/?ordering=starts_at${q}`),api('clients/'),api('locations/'),api('positions/'),api('orders/'),api('workers/?ordering=user__last_name')]);
    setRows(unpack(s)); setClients(unpack(c)); setLocations(unpack(l)); setPositions(unpack(p)); setOrders(unpack(o)); setWorkers(unpack(w).filter((item:any)=>item.active!==false&&!isSyntheticWorker(item)));
  }
  useEffect(()=>{void load();},[tab]);

  const visible=useMemo(()=>rows.filter((x:any)=>{
    if(user.role==='client') return true;
    if(!isManager(user)||tab==='all') return true;
    // Operational planning should not start with already-ended shifts. Historical
    // rows remain available under "Alle" for audit and lookup.
    if(x.ends_at && new Date(x.ends_at).getTime()<Date.now()) return false;
    if(tab==='draft') return x.status==='draft';
    if(tab==='filled') return x.status!=='draft'&&Number(x.open_count||0)===0;
    return x.status==='published'&&Number(x.open_count||0)>0;
  }),[rows,tab,user]);

  async function act(path:string,msg:string){setBusy(true);try{await api(path,{method:'POST',body:'{}'});setToast(msg);await load();}catch(e:any){setToast(e.message);}finally{setBusy(false);}}
  function create(){setEditing(undefined);setForm({required_count:1,break_minutes:0,publish_now:true,workers:[]});setModal(true);}
  function edit(x:any){setEditing(x.id);setForm({...x,workers:(x.assigned_workers||[]).map((worker:any)=>worker.id),starts_at:x.starts_at?.slice(0,16),ends_at:x.ends_at?.slice(0,16),publish_now:x.status==='published'});setModal(true);}
  function setShiftDateTime(field:'starts_at'|'ends_at',next:string){
    setForm((current:any)=>{
      const updated={...current,[field]:next};
      if(field==='starts_at'&&next){
        const start=wallClockMs(next);
        const currentEnd=current.ends_at?wallClockMs(current.ends_at):undefined;
        if(!currentEnd||currentEnd<=start){
          updated.ends_at=fromWallClockMs(start+4*60*60*1000);
        }
      }
      return updated;
    });
  }
  async function save(){
    setBusy(true);
    let createdId:string|undefined;
    try{
      if(!form.client||!form.location||!form.position||!form.starts_at||!form.ends_at) throw new Error('Bitte alle Pflichtfelder ausfüllen.');
      const start=wallClockMs(form.starts_at), end=wallClockMs(form.ends_at);
      if(!(end>start)) throw new Error('Das Ende muss nach dem Beginn liegen.');
      const assignedWorkers=Array.isArray(form.workers)?form.workers.filter(Boolean):[];
      const requiredCount=Math.max(1,Number(form.required_count||1));
      if(assignedWorkers.length>requiredCount) throw new Error('Mehr Mitarbeiter ausgewählt als benötigte Plätze.');
      const baseStatus=assignedWorkers.length===requiredCount?'draft':form.publish_now?'published':'draft';
      const p:any={client:form.client,location:form.location,position:form.position,order:form.order||null,starts_at:form.starts_at,ends_at:form.ends_at,break_minutes:Number(form.break_minutes||0),required_count:requiredCount,notes:form.notes||'',status:baseStatus};
      const saved:any=await api(editing?`shifts/${editing}/`:'shifts/',{method:editing?'PATCH':'POST',body:JSON.stringify(p)});
      if(!editing) createdId=String(saved.id);
      await api(`shifts/${saved.id}/assign/`,{method:'POST',body:JSON.stringify({workers:assignedWorkers,publish_remaining:!!form.publish_now})});
      createdId=undefined;
      setModal(false);
      setToast(assignedWorkers.length?`${assignedWorkers.length} Mitarbeiter direkt zugewiesen.`:'Personalbedarf gespeichert.');
      await load();
    }catch(e:any){
      if(createdId){
        try{await api(`shifts/${createdId}/`,{method:'DELETE'});}catch{/* Best effort rollback; original error stays visible. */}
        await load();
      }
      setToast(e.message);
    }finally{setBusy(false);}
  }
  function confirmRelease(){const id=releaseTarget?.id;setReleaseTarget(undefined);if(id) void act(`shifts/${id}/release/`,'Schicht freigegeben.');}

  const workerView=user.role==='worker';
  const clientView=user.role==='client';
  const eyebrow=workerView?'MEINE ARBEIT':clientView?'KUNDENPORTAL':'PERSONALPLANUNG';
  const title=workerView?'Schichten':clientView?'Einsätze':'Personalbedarf & Schichten';
  const intro=workerView?'Freie Einsätze finden und eigene Schichten verwalten.':clientView?'Geplante Einsätze und aktueller Besetzungsstatus für Ihre Aufträge.':'Kundenbedarf erstellen, Mitarbeiter direkt zuweisen oder Restplätze als OpenShift veröffentlichen.';
  const searchPlaceholder=clientView?'Einsatz, Ort oder Position suchen …':'Kunde, Ort, Position oder Auftrag suchen …';

  return <div className="sv2">
    <div className="sv2-title"><div><small>{eyebrow}</small><h1>{title}</h1><p>{intro}</p></div>{isManager(user)&&<IonButton onClick={create}><IonIcon slot="start" icon={addOutline}/>Personalbedarf</IonButton>}</div>
    <div className="sv2-search"><IonSearchbar value={search} debounce={350} placeholder={searchPlaceholder} onIonInput={e=>setSearch(String(val(e)))} onIonChange={()=>void load()}/><IonButton fill="outline" onClick={()=>void load()}><IonIcon slot="icon-only" icon={refreshOutline}/></IonButton></div>
    {workerView?<IonSegment scrollable value={tab} onIonChange={e=>setTab(String(val(e)))}><IonSegmentButton value="available"><IonLabel>Verfügbare Schichten</IonLabel></IonSegmentButton><IonSegmentButton value="mine"><IonLabel>Meine Schichten</IonLabel></IonSegmentButton></IonSegment>:isManager(user)?<IonSegment scrollable value={tab} onIonChange={e=>setTab(String(val(e)))}><IonSegmentButton value="open"><IonLabel>Offen</IonLabel></IonSegmentButton><IonSegmentButton value="filled"><IonLabel>Voll besetzt</IonLabel></IonSegmentButton><IonSegmentButton value="draft"><IonLabel>Entwürfe</IonLabel></IonSegmentButton><IonSegmentButton value="all"><IonLabel>Alle</IonLabel></IonSegmentButton></IonSegment>:null}
    <div className="sv2-list">{visible.map((x:any)=>{const mine=workerView&&tab==='mine';const open=x.status==='published'&&Number(x.open_count||0)>0;const assigned=x.assigned_workers||[];return <article className={`sv2-card ${mine?'mine':''}`} key={x.id}>
      <div className="sv2-date"><b>{berlinDay(x.starts_at)}</b><span>{berlinMonth(x.starts_at)}</span></div>
      <div className="sv2-body"><small>{x.client_name}</small><h3>{x.position_name}</h3><p><IonIcon icon={timeOutline}/> {tm(x.starts_at)}–{tm(x.ends_at)} · {x.break_minutes||0} Min.</p><p><IonIcon icon={locationOutline}/> {x.location_name}</p>{assigned.length>0&&<p><b>Zugewiesen:</b> {assigned.map((worker:any)=>worker.name).join(', ')}</p>}<div className="sv2-meter"><span style={{width:`${Math.min(100,(Number(x.filled_count||0)/Number(x.required_count||1))*100)}%`}}/></div><em>{x.filled_count||0}/{x.required_count||1} besetzt · {x.open_count||0} frei</em></div>
      <div className="sv2-side"><IonBadge color={x.status==='draft'?'medium':open?'primary':'success'}>{x.status==='draft'?'Entwurf':open?'Offen':'Voll'}</IonBadge>{workerView&&!mine&&open&&<IonButton disabled={busy} onClick={()=>void act(`shifts/${x.id}/claim/`,'Schicht übernommen.')}><IonIcon slot="start" icon={checkmarkCircleOutline}/>Übernehmen</IonButton>}{workerView&&mine&&<IonButton fill="outline" color="medium" disabled={busy} onClick={()=>setReleaseTarget(x)}>Freigeben</IonButton>}{isManager(user)&&x.status==='draft'&&Number(x.open_count||0)>0&&<IonButton size="small" onClick={()=>void act(`shifts/${x.id}/publish/`,'OpenShift veröffentlicht.')}>Veröffentlichen</IonButton>}{isManager(user)&&<IonButton size="small" fill="clear" onClick={()=>edit(x)}>Bearbeiten</IonButton>}</div>
    </article>})}{!visible.length&&<div className="sv2-empty"><h3>Keine passenden Einsätze</h3><p>Suche oder Filter ändern.</p></div>}</div>
    <IonModal isOpen={modal} onDidDismiss={()=>setModal(false)}><div className="sv2-modal"><div className="sv2-modal-head"><h2>{editing?'Personalbedarf bearbeiten':'Personalbedarf anlegen'}</h2><IonButton fill="clear" onClick={()=>setModal(false)}>Schließen</IonButton></div><div className="sv2-form">
      <IonSelect fill="outline" label="Kunde *" labelPlacement="floating" value={form.client} onIonChange={e=>setForm({...form,client:val(e)})}>{clients.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <IonSelect fill="outline" label="Auftrag" labelPlacement="floating" value={form.order} onIonChange={e=>setForm({...form,order:val(e)})}><IonSelectOption value="">Ohne Auftrag</IonSelectOption>{orders.filter(x=>!form.client||x.client===form.client).map(x=><IonSelectOption key={x.id} value={x.id}>{x.title}</IonSelectOption>)}</IonSelect>
      <IonSelect fill="outline" label="Einsatzort *" labelPlacement="floating" value={form.location} onIonChange={e=>setForm({...form,location:val(e)})}>{locations.filter(x=>!form.client||!x.client||x.client===form.client).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <IonSelect fill="outline" label="Position *" labelPlacement="floating" value={form.position} onIonChange={e=>setForm({...form,position:val(e)})}>{positions.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <FriendlyDateTime label="Beginn" value={form.starts_at} onChange={next=>setShiftDateTime('starts_at',next)}/>
      <FriendlyDateTime label="Ende" value={form.ends_at} onChange={next=>setShiftDateTime('ends_at',next)}/>
      <IonInput fill="outline" type="number" min="1" label="Benötigte Mitarbeiter *" labelPlacement="floating" value={form.required_count} onIonInput={e=>setForm({...form,required_count:Math.max(Number(val(e)||1),(form.workers||[]).length)})}/><IonInput fill="outline" type="number" min="0" label="Pause (Min.)" labelPlacement="floating" value={form.break_minutes} onIonInput={e=>setForm({...form,break_minutes:val(e)})}/>
      <IonSelect className="full" multiple interface="alert" fill="outline" label="Mitarbeiter direkt zuweisen (optional)" labelPlacement="floating" value={form.workers||[]} onIonChange={e=>{const selected=Array.isArray(val(e))?val(e):[];setForm({...form,workers:selected,required_count:Math.max(Number(form.required_count||1),selected.length)});}}>
        {workers.map(worker=><IonSelectOption key={worker.id} value={worker.id}>{workerLabel(worker)} · {worker.employee_number}</IonSelectOption>)}
      </IonSelect>
      {(form.workers||[]).length>0&&<div className="full" style={{fontSize:13,color:'#667085',marginTop:-6}}>{(form.workers||[]).length} von {form.required_count||1} Plätzen werden direkt zugewiesen. Freie Restplätze können als OpenShift veröffentlicht werden.</div>}
      <IonTextarea className="full" fill="outline" label="Hinweise für Mitarbeiter" labelPlacement="floating" value={form.notes} onIonInput={e=>setForm({...form,notes:val(e)})}/><label className="sv2-toggle full">{(form.workers||[]).length>0?'Restliche freie Plätze als OpenShift veröffentlichen':'Direkt als OpenShift veröffentlichen'} <IonToggle checked={!!form.publish_now} onIonChange={e=>setForm({...form,publish_now:e.detail.checked})}/></label>
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setModal(false)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>void save()}>Speichern</IonButton></div></div></IonModal>
    <IonAlert isOpen={!!releaseTarget} onDidDismiss={()=>setReleaseTarget(undefined)} header="Schicht freigeben?" message={releaseTarget?`${releaseTarget.position_name || 'Diese Schicht'} wird wieder für andere Mitarbeiter verfügbar.`:''} buttons={[{text:'Abbrechen',role:'cancel'},{text:'Freigeben',role:'destructive',handler:confirmRelease}]}/>
    <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={()=>setToast('')}/>
  </div>;
}

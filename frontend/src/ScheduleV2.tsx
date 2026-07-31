import React, { useEffect, useMemo, useState } from 'react';
import { IonBadge, IonButton, IonIcon, IonInput, IonLabel, IonModal, IonSearchbar, IonSegment, IonSegmentButton, IonSelect, IonSelectOption, IonTextarea, IonToast, IonToggle } from '@ionic/react';
import { addOutline, checkmarkCircleOutline, locationOutline, refreshOutline, timeOutline } from 'ionicons/icons';
import { api, User } from './api';
import './schedule-v2.css';

const unpack = (x:any):any[] => x?.results || x || [];
const val = (e:any) => e.detail.value ?? '';
const isManager = (u:User) => ['admin','manager'].includes(u.role);
const tm = (x:string) => new Date(x).toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});

export default function ScheduleV2({user}:{user:User}) {
  const [rows,setRows]=useState<any[]>([]), [clients,setClients]=useState<any[]>([]), [locations,setLocations]=useState<any[]>([]), [positions,setPositions]=useState<any[]>([]), [orders,setOrders]=useState<any[]>([]);
  const [tab,setTab]=useState(user.role==='worker'?'available':'open'), [search,setSearch]=useState(''), [modal,setModal]=useState(false), [editing,setEditing]=useState<string>(), [busy,setBusy]=useState(false), [toast,setToast]=useState('');
  const [form,setForm]=useState<any>({required_count:1,break_minutes:0,publish_now:true});

  async function load() {
    const q=search.trim()?`&search=${encodeURIComponent(search.trim())}`:'';
    if(user.role==='worker') {
      const endpoint=tab==='mine'?'shifts/mine/':'shifts/available/';
      setRows(unpack(await api(`${endpoint}?ordering=starts_at${q}`))); return;
    }
    const [s,c,l,p,o]=await Promise.all([api(`shifts/?ordering=starts_at${q}`),api('clients/'),api('locations/'),api('positions/'),api('orders/')]);
    setRows(unpack(s)); setClients(unpack(c)); setLocations(unpack(l)); setPositions(unpack(p)); setOrders(unpack(o));
  }
  useEffect(()=>{void load();},[tab]);

  const visible=useMemo(()=>rows.filter((x:any)=>{
    if(!isManager(user)||tab==='all') return true;
    if(tab==='draft') return x.status==='draft';
    if(tab==='filled') return x.status!=='draft'&&Number(x.available_count||0)===0;
    return x.status!=='draft'&&Number(x.available_count||0)>0;
  }),[rows,tab,user]);

  async function act(path:string,msg:string){setBusy(true);try{await api(path,{method:'POST',body:'{}'});setToast(msg);await load();}catch(e:any){setToast(e.message);}finally{setBusy(false);}}
  function create(){setEditing(undefined);setForm({required_count:1,break_minutes:0,publish_now:true});setModal(true);}
  function edit(x:any){setEditing(x.id);setForm({...x,starts_at:x.starts_at?.slice(0,16),ends_at:x.ends_at?.slice(0,16),publish_now:x.status!=='draft'});setModal(true);}
  async function save(){setBusy(true);try{const p:any={client:form.client,location:form.location,position:form.position,order:form.order||null,starts_at:form.starts_at,ends_at:form.ends_at,break_minutes:Number(form.break_minutes||0),required_count:Number(form.required_count||1),notes:form.notes||'',status:form.publish_now?'published':'draft'};await api(editing?`shifts/${editing}/`:'shifts/',{method:editing?'PATCH':'POST',body:JSON.stringify(p)});setModal(false);setToast('Personalbedarf gespeichert.');await load();}catch(e:any){setToast(e.message);}finally{setBusy(false);}}

  return <div className="sv2">
    <div className="sv2-title"><div><small>{user.role==='worker'?'MEINE ARBEIT':'PERSONALPLANUNG'}</small><h1>{user.role==='worker'?'Schichten':'Personalbedarf & Schichten'}</h1><p>{user.role==='worker'?'Freie Einsätze finden und eigene Schichten verwalten.':'Kundenbedarf erstellen, prüfen und als OpenShift veröffentlichen.'}</p></div>{isManager(user)&&<IonButton onClick={create}><IonIcon slot="start" icon={addOutline}/>Personalbedarf</IonButton>}</div>
    <div className="sv2-search"><IonSearchbar value={search} debounce={350} placeholder="Kunde, Ort, Position oder Auftrag suchen …" onIonInput={e=>setSearch(String(val(e)))} onIonChange={()=>void load()}/><IonButton fill="outline" onClick={()=>void load()}><IonIcon slot="icon-only" icon={refreshOutline}/></IonButton></div>
    <IonSegment scrollable value={tab} onIonChange={e=>setTab(String(val(e)))}>{user.role==='worker'?<><IonSegmentButton value="available"><IonLabel>Verfügbare Schichten</IonLabel></IonSegmentButton><IonSegmentButton value="mine"><IonLabel>Meine Schichten</IonLabel></IonSegmentButton></>:<><IonSegmentButton value="open"><IonLabel>Offen</IonLabel></IonSegmentButton><IonSegmentButton value="filled"><IonLabel>Voll besetzt</IonLabel></IonSegmentButton><IonSegmentButton value="draft"><IonLabel>Entwürfe</IonLabel></IonSegmentButton><IonSegmentButton value="all"><IonLabel>Alle</IonLabel></IonSegmentButton></>}</IonSegment>
    <div className="sv2-list">{visible.map((x:any)=><article className={`sv2-card ${x.my_assignment?'mine':''}`} key={x.id}>
      <div className="sv2-date"><b>{new Date(x.starts_at).getDate()}</b><span>{new Date(x.starts_at).toLocaleString('de-DE',{month:'short'})}</span></div>
      <div className="sv2-body"><small>{x.client_name}</small><h3>{x.position_name}</h3><p><IonIcon icon={timeOutline}/> {tm(x.starts_at)}–{tm(x.ends_at)} · {x.break_minutes||0} Min.</p><p><IonIcon icon={locationOutline}/> {x.location_name}</p><div className="sv2-meter"><span style={{width:`${Math.min(100,(Number(x.assigned_count||0)/Number(x.required_count||1))*100)}%`}}/></div><em>{x.assigned_count||0}/{x.required_count||1} besetzt · {x.available_count||0} frei</em>{isManager(user)&&x.assignments?.some((a:any)=>a.worker_name)&&<div className="sv2-people">{x.assignments.filter((a:any)=>a.worker_name).map((a:any)=><i key={a.id}>{a.worker_name}</i>)}</div>}</div>
      <div className="sv2-side"><IonBadge color={x.status==='draft'?'medium':x.available_count>0?'primary':'success'}>{x.status==='draft'?'Entwurf':x.available_count>0?'Offen':'Voll'}</IonBadge>{user.role==='worker'&&!x.my_assignment&&x.available_count>0&&<IonButton disabled={busy} onClick={()=>void act(`shifts/${x.id}/claim/`,'Schicht übernommen.')}><IonIcon slot="start" icon={checkmarkCircleOutline}/>Übernehmen</IonButton>}{user.role==='worker'&&x.my_assignment&&<IonButton fill="outline" color="medium" disabled={busy} onClick={()=>window.confirm('Schicht zurück in den Pool geben?')&&void act(`shifts/${x.id}/release/`,'Schicht freigegeben.')}>Freigeben</IonButton>}{isManager(user)&&x.status==='draft'&&<IonButton size="small" onClick={()=>void act(`shifts/${x.id}/publish/`,'OpenShift veröffentlicht.')}>Veröffentlichen</IonButton>}{isManager(user)&&<IonButton size="small" fill="clear" onClick={()=>edit(x)}>Bearbeiten</IonButton>}</div>
    </article>)}{!visible.length&&<div className="sv2-empty"><h3>Keine passenden Schichten</h3><p>Suche oder Filter ändern.</p></div>}</div>
    <IonModal isOpen={modal} onDidDismiss={()=>setModal(false)}><div className="sv2-modal"><div className="sv2-modal-head"><h2>{editing?'Personalbedarf bearbeiten':'Personalbedarf anlegen'}</h2><IonButton fill="clear" onClick={()=>setModal(false)}>Schließen</IonButton></div><div className="sv2-form">
      <IonSelect fill="outline" label="Kunde *" labelPlacement="floating" value={form.client} onIonChange={e=>setForm({...form,client:val(e)})}>{clients.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <IonSelect fill="outline" label="Auftrag" labelPlacement="floating" value={form.order} onIonChange={e=>setForm({...form,order:val(e)})}><IonSelectOption value="">Ohne Auftrag</IonSelectOption>{orders.filter(x=>!form.client||x.client===form.client).map(x=><IonSelectOption key={x.id} value={x.id}>{x.title}</IonSelectOption>)}</IonSelect>
      <IonSelect fill="outline" label="Einsatzort *" labelPlacement="floating" value={form.location} onIonChange={e=>setForm({...form,location:val(e)})}>{locations.filter(x=>!form.client||!x.client||x.client===form.client).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <IonSelect fill="outline" label="Position *" labelPlacement="floating" value={form.position} onIonChange={e=>setForm({...form,position:val(e)})}>{positions.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <IonInput fill="outline" type="datetime-local" label="Beginn *" labelPlacement="floating" value={form.starts_at} onIonInput={e=>setForm({...form,starts_at:val(e)})}/><IonInput fill="outline" type="datetime-local" label="Ende *" labelPlacement="floating" value={form.ends_at} onIonInput={e=>setForm({...form,ends_at:val(e)})}/>
      <IonInput fill="outline" type="number" min="1" label="Benötigte Mitarbeiter *" labelPlacement="floating" value={form.required_count} onIonInput={e=>setForm({...form,required_count:val(e)})}/><IonInput fill="outline" type="number" min="0" label="Pause (Min.)" labelPlacement="floating" value={form.break_minutes} onIonInput={e=>setForm({...form,break_minutes:val(e)})}/>
      <IonTextarea className="full" fill="outline" label="Hinweise für Mitarbeiter" labelPlacement="floating" value={form.notes} onIonInput={e=>setForm({...form,notes:val(e)})}/><label className="sv2-toggle full">Direkt als OpenShift veröffentlichen <IonToggle checked={!!form.publish_now} onIonChange={e=>setForm({...form,publish_now:e.detail.checked})}/></label>
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setModal(false)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>void save()}>Speichern</IonButton></div></div></IonModal>
    <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={()=>setToast('')}/>
  </div>;
}

import React, { useEffect, useState } from 'react';
import { Capacitor } from '@capacitor/core';
import { IonButton, IonIcon, IonInput, IonModal, IonSelect, IonSelectOption, IonTextarea, IonToast } from '@ionic/react';
import { addOutline, locationOutline, trashOutline } from 'ionicons/icons';
import { api, User } from './api';
import PortalAccessPanel from './PortalAccessPanel';
import NotificationPushSettings from './NotificationPushSettings';
import { enrichLocationPayload } from './locationPicker';

const unpack=(data:any):any[]=>data?.results||data||[];
const value=(event:any)=>event.detail.value??'';

export default function Settings({user}:{user:User}){
  const [clients,setClients]=useState<any[]>([]),[locations,setLocations]=useState<any[]>([]),[positions,setPositions]=useState<any[]>([]);
  const [modal,setModal]=useState(''),[busy,setBusy]=useState(false),[toast,setToast]=useState('');
  const [locationForm,setLocationForm]=useState<any>({geofence_radius_m:250}),[positionForm,setPositionForm]=useState<any>({color:'#155eef'});
  const [csvFile,setCsvFile]=useState<File>(),[csvType,setCsvType]=useState('workers');
  const [policy,setPolicy]=useState<any>();
  const webOnly=!Capacitor.isNativePlatform();

  async function load(){
    const [c,l,p]=await Promise.all([api('clients/?ordering=name'),api('locations/'),api('positions/')]);
    setClients(unpack(c).filter((item:any)=>item.active!==false));
    setLocations(unpack(l).filter((item:any)=>item.active!==false));
    setPositions(unpack(p).filter((item:any)=>item.active!==false));
  }
  useEffect(()=>{void load();},[]);
  useEffect(()=>{
    if(!webOnly||!['admin','manager'].includes(user.role))return;
    api('premium/scheduling-policy/').then(setPolicy).catch((e:any)=>setToast(e.message));
  },[user.role,webOnly]);

  async function submit(path:string,payload:any,done:()=>void){
    setBusy(true);try{const finalPayload=path==='locations/'?await enrichLocationPayload(payload):payload;await api(path,{method:'POST',body:JSON.stringify(finalPayload)});done();setModal('');await load();setToast('Einstellung wurde gespeichert.');}catch(e:any){setToast(e.message);}finally{setBusy(false);}
  }
  async function remove(kind:'locations'|'positions',id:string){
    if(!window.confirm('Diesen Stammdatensatz wirklich löschen?'))return;
    try{await api(`${kind}/${id}/`,{method:'DELETE'});await load();setToast('Datensatz wurde gelöscht.');}catch(e:any){setToast(e.message);}
  }
  async function importCsv(){
    if(!csvFile)return;setBusy(true);const form=new FormData();form.append('file',csvFile);
    try{const result:any=await api(`${csvType}/import_csv/`,{method:'POST',body:form});setToast(`${result.created} Datensätze importiert. ${result.errors?.length||0} Fehler.`);setModal('');setCsvFile(undefined);await load();}catch(e:any){setToast(e.message);}finally{setBusy(false);}
  }
  async function saveSameDayRules(){
    if(!policy)return;
    setBusy(true);
    try{
      const saved:any=await api('premium/scheduling-policy/',{method:'PATCH',body:JSON.stringify({
        min_hours_same_day:policy.min_hours_same_day,
        allow_multiple_shifts_per_day:!!policy.allow_multiple_shifts_per_day,
      })});
      setPolicy(saved);setToast('Planungsregeln wurden gespeichert.');
    }catch(e:any){setToast(e.message);}finally{setBusy(false);}
  }

  return <>
    <div className="title"><div><h1>Einstellungen</h1><p>Stammdaten, Portalzugänge und administrative Imports.</p></div><IonButton fill="outline" onClick={()=>setModal('csv')}>CSV-Import</IonButton></div>
    {webOnly&&policy&&['admin','manager'].includes(user.role)&&<section className="panel" style={{marginBottom:18}}>
      <div className="section-head">
        <div>
          <h3>Planungsregeln</h3>
          <p>Regeln für mehrere Einsätze eines Mitarbeiters am selben Kalendertag.</p>
        </div>
        <IonButton size="small" disabled={busy} onClick={()=>void saveSameDayRules()}>Speichern</IonButton>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(240px,1fr))',gap:14,alignItems:'end'}}>
        <label>
          <span style={{display:'block',fontSize:12,fontWeight:700,marginBottom:6}}>Ruhezeit zwischen Schichten am selben Tag</span>
          <IonInput fill="outline" type="number" min="0" step="0.5" value={policy.min_hours_same_day} onIonInput={e=>setPolicy({...policy,min_hours_same_day:value(e)})}>
            <div slot="end" style={{paddingRight:10,color:'#667085'}}>Std.</div>
          </IonInput>
        </label>
        <label style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:16,minHeight:56,padding:'0 14px',border:'1px solid #d0d5dd',borderRadius:12}}>
          <div><b style={{display:'block'}}>Mehrere Schichten pro Tag</b><small style={{color:'#667085'}}>Mehr als einen Einsatz pro Mitarbeiter erlauben.</small></div>
          <input type="checkbox" checked={!!policy.allow_multiple_shifts_per_day} onChange={e=>setPolicy({...policy,allow_multiple_shifts_per_day:e.currentTarget.checked})}/>
        </label>
      </div>
    </section>}
    <PortalAccessPanel />
    <NotificationPushSettings role={user.role} />
    <div className="columns master-data">
      <div className="panel"><div className="section-head"><div><h3>Einsatzorte</h3><p>Adressen und GPS-Geofences.</p></div><IonButton fill="outline" size="small" onClick={()=>setModal('location')}><IonIcon slot="start" icon={addOutline}/>Standort</IonButton></div>
        {locations.map(location=><div className="row" key={location.id}><IonIcon icon={locationOutline}/><div className="grow"><b>{location.name}</b><p>{location.client_name||'Ohne Kunde'} · {location.address}</p></div><span>{location.geofence_radius_m} m</span><IonButton fill="clear" color="danger" onClick={()=>remove('locations',location.id)}><IonIcon icon={trashOutline}/></IonButton></div>)}
        {!locations.length&&<div className="empty">Noch keine Einsatzorte.</div>}
      </div>
      <div className="panel"><div className="section-head"><div><h3>Positionen</h3><p>Aktive Funktionen für die Dienstplanung.</p></div><IonButton fill="outline" size="small" onClick={()=>setModal('position')}><IonIcon slot="start" icon={addOutline}/>Position</IonButton></div>
        <div className="chips">{positions.map(position=><div className="position-chip" key={position.id}><span style={{background:position.color}}/>{position.name}<button onClick={()=>remove('positions',position.id)} aria-label="Löschen">×</button></div>)}</div>
        {!positions.length&&<div className="empty">Noch keine Positionen.</div>}
      </div>
    </div>

    <IonModal isOpen={modal==='location'} onDidDismiss={()=>setModal('')}><div className="sv2-modal"><div className="sv2-modal-head"><h2>Einsatzort anlegen</h2><IonButton fill="clear" onClick={()=>setModal('')}>Schließen</IonButton></div><div className="sv2-form">
      <IonSelect fill="outline" label="Kunde" labelPlacement="floating" value={locationForm.client} onIonChange={e=>setLocationForm({...locationForm,client:value(e)})}><IonSelectOption value="">Ohne feste Zuordnung</IonSelectOption>{clients.map(client=><IonSelectOption key={client.id} value={client.id}>{client.name}</IonSelectOption>)}</IonSelect>
      <IonInput fill="outline" label="Bezeichnung *" labelPlacement="floating" value={locationForm.name} onIonInput={e=>setLocationForm({...locationForm,name:value(e)})}/>
      <IonTextarea fill="outline" label="Adresse *" labelPlacement="floating" value={locationForm.address} onIonInput={e=>setLocationForm({...locationForm,address:value(e)})}/>
      <IonInput fill="outline" type="number" label="Geofence-Radius in Metern" labelPlacement="floating" value={locationForm.geofence_radius_m} onIonInput={e=>setLocationForm({...locationForm,geofence_radius_m:value(e)})}/>
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setModal('')}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>submit('locations/',{...locationForm,client:locationForm.client||null},()=>setLocationForm({geofence_radius_m:250}))}>Speichern</IonButton></div></div></IonModal>

    <IonModal isOpen={modal==='position'} onDidDismiss={()=>setModal('')}><div className="sv2-modal"><div className="sv2-modal-head"><h2>Position anlegen</h2><IonButton fill="clear" onClick={()=>setModal('')}>Schließen</IonButton></div><div className="sv2-form">
      <IonInput fill="outline" label="Bezeichnung *" labelPlacement="floating" value={positionForm.name} onIonInput={e=>setPositionForm({...positionForm,name:value(e)})}/>
      <IonInput fill="outline" {...({type:'color'} as any)} label="Farbe" labelPlacement="floating" value={positionForm.color} onIonInput={e=>setPositionForm({...positionForm,color:value(e)})}/>
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setModal('')}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>submit('positions/',positionForm,()=>setPositionForm({color:'#155eef'}))}>Speichern</IonButton></div></div></IonModal>

    <IonModal isOpen={modal==='csv'} onDidDismiss={()=>setModal('')}><div className="sv2-modal"><div className="sv2-modal-head"><h2>Stammdaten aus CSV importieren</h2><IonButton fill="clear" onClick={()=>setModal('')}>Schließen</IonButton></div><div className="sv2-form">
      <IonSelect fill="outline" label="Datentyp" labelPlacement="floating" value={csvType} onIonChange={e=>setCsvType(String(value(e)))}><IonSelectOption value="workers">Mitarbeiter</IonSelectOption><IonSelectOption value="clients">Kunden</IonSelectOption></IonSelect>
      <label className="file-field full"><span>CSV-Datei auswählen</span><input type="file" accept=".csv,text/csv" onChange={e=>setCsvFile(e.target.files?.[0])}/><b>{csvFile?.name||'Keine Datei ausgewählt'}</b></label>
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setModal('')}>Abbrechen</IonButton><IonButton disabled={busy||!csvFile} onClick={()=>void importCsv()}>Importieren</IonButton></div></div></IonModal>
    <IonToast isOpen={!!toast} message={toast} duration={1000} onDidDismiss={()=>setToast('')}/>
  </>;
}

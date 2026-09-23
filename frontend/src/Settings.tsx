import React, { useEffect, useState } from 'react';
import { Capacitor } from '@capacitor/core';
import { IonButton, IonIcon, IonInput, IonModal, IonSelect, IonSelectOption, IonTextarea, IonToast, IonToggle } from '@ionic/react';
import { addOutline, locationOutline, trashOutline } from 'ionicons/icons';
import { api, User } from './api';
import PortalAccessPanel from './PortalAccessPanel';
import NotificationPushSettings from './NotificationPushSettings';
import { enrichLocationPayload } from './locationPicker';
import './settings-planning-rules.css';

const unpack=(data:any):any[]=>data?.results||data||[];
const value=(event:any)=>event.detail.value??'';

export default function Settings({user}:{user:User}){
  const [clients,setClients]=useState<any[]>([]),[locations,setLocations]=useState<any[]>([]),[positions,setPositions]=useState<any[]>([]);
  const [modal,setModal]=useState(''),[busy,setBusy]=useState(false),[toast,setToast]=useState('');
  const [locationForm,setLocationForm]=useState<any>({geofence_radius_m:250}),[positionForm,setPositionForm]=useState<any>({color:'#155eef'});
  const [csvFile,setCsvFile]=useState<File>(),[csvType,setCsvType]=useState('workers');
  const [policy,setPolicy]=useState<any>();
  const webOnly=!Capacitor.isNativePlatform();
  const showPlanningRules=webOnly&&user.role==='admin';

  async function load(){
    const [c,l,p]=await Promise.all([api('clients/?ordering=name'),api('locations/'),api('positions/')]);
    setClients(unpack(c).filter((item:any)=>item.active!==false));
    setLocations(unpack(l).filter((item:any)=>item.active!==false));
    setPositions(unpack(p).filter((item:any)=>item.active!==false));
  }
  useEffect(()=>{void load();},[]);
  useEffect(()=>{
    if(!showPlanningRules)return;
    api('premium/scheduling-policy/').then(setPolicy).catch((e:any)=>setToast(e.message));
  },[showPlanningRules]);

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
  async function savePlanningRules(){
    if(!policy)return;
    setBusy(true);
    try{
      const saved:any=await api('premium/scheduling-policy/',{method:'PATCH',body:JSON.stringify({
        min_hours_same_day:policy.min_hours_same_day,
        min_hours_between_days:policy.min_hours_between_days,
        max_hours_per_day:policy.max_hours_per_day,
        max_hours_per_week:policy.max_hours_per_week,
        max_days_in_row:policy.max_days_in_row,
        max_days_per_week:policy.max_days_per_week,
        respect_worker_monthly_hours:!!policy.respect_worker_monthly_hours,
        allow_multiple_shifts_per_day:!!policy.allow_multiple_shifts_per_day,
        allow_overlapping_open_shifts:!!policy.allow_overlapping_open_shifts,
      })});
      setPolicy(saved);setToast('Planungsregeln wurden gespeichert.');
    }catch(e:any){setToast(e.message);}finally{setBusy(false);}
  }

  return <>
    <div className="title"><div><h1>Einstellungen</h1><p>Stammdaten, Portalzugänge und administrative Imports.</p></div><IonButton fill="outline" onClick={()=>setModal('csv')}>CSV-Import</IonButton></div>
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

    {showPlanningRules&&policy&&<section className="admin-planning-rules" data-testid="admin-planning-rules">
      <div className="admin-planning-rules__head">
        <div>
          <small className="admin-planning-rules__eyebrow">DIENSTPLAN · ADMIN</small>
          <h3>Planungsregeln & Arbeitszeitgrenzen</h3>
          <p>Diese Werte werden bei Zuweisungen und Schichtwechseln direkt geprüft. Änderungen gelten nach dem Speichern sofort für neue Prüfungen.</p>
        </div>
        <IonButton className="admin-planning-rules__save" size="small" disabled={busy} onClick={()=>void savePlanningRules()}>Regeln speichern</IonButton>
      </div>

      <div className="admin-planning-rules__body">
        <div className="admin-planning-rules__group">
          <div className="admin-planning-rules__group-head">
            <b>Ruhezeiten & Grenzen</b>
            <span>Zeitliche Mindestabstände und maximale Einsatzgrenzen.</span>
          </div>
          <div className="admin-planning-rules__number-grid">
            <label className="admin-planning-rules__field">
              <span>Ruhezeit zwischen Schichten am selben Tag</span>
              <IonInput fill="outline" type="number" min="0" step="0.5" value={policy.min_hours_same_day} onIonInput={e=>setPolicy({...policy,min_hours_same_day:value(e)})}>
                <em slot="end" className="admin-planning-rules__unit">Std.</em>
              </IonInput>
            </label>
            <label className="admin-planning-rules__field">
              <span>Ruhezeit zwischen Arbeitstagen</span>
              <IonInput fill="outline" type="number" min="0" step="0.5" value={policy.min_hours_between_days} onIonInput={e=>setPolicy({...policy,min_hours_between_days:value(e)})}>
                <em slot="end" className="admin-planning-rules__unit">Std.</em>
              </IonInput>
            </label>
            <label className="admin-planning-rules__field">
              <span>Maximale Stunden pro Tag</span>
              <IonInput fill="outline" type="number" min="0" step="0.5" value={policy.max_hours_per_day} onIonInput={e=>setPolicy({...policy,max_hours_per_day:value(e)})}>
                <em slot="end" className="admin-planning-rules__unit">Std.</em>
              </IonInput>
            </label>
            <label className="admin-planning-rules__field">
              <span>Maximale Stunden pro Woche</span>
              <IonInput fill="outline" type="number" min="0" step="0.5" value={policy.max_hours_per_week} onIonInput={e=>setPolicy({...policy,max_hours_per_week:value(e)})}>
                <em slot="end" className="admin-planning-rules__unit">Std.</em>
              </IonInput>
            </label>
            <label className="admin-planning-rules__field">
              <span>Maximale Arbeitstage in Folge</span>
              <IonInput fill="outline" type="number" min="1" step="1" value={policy.max_days_in_row} onIonInput={e=>setPolicy({...policy,max_days_in_row:value(e)})}>
                <em slot="end" className="admin-planning-rules__unit">Tage</em>
              </IonInput>
            </label>
            <label className="admin-planning-rules__field">
              <span>Maximale Arbeitstage pro Woche</span>
              <IonInput fill="outline" type="number" min="1" max="7" step="1" value={policy.max_days_per_week} onIonInput={e=>setPolicy({...policy,max_days_per_week:value(e)})}>
                <em slot="end" className="admin-planning-rules__unit">Tage</em>
              </IonInput>
            </label>
          </div>
        </div>

        <div className="admin-planning-rules__group">
          <div className="admin-planning-rules__group-head">
            <b>Planungsoptionen</b>
            <span>Welche Zuweisungen bei der Dienstplanung zugelassen werden.</span>
          </div>
          <div className="admin-planning-rules__toggles">
            <div className="admin-planning-rules__toggle">
              <div className="admin-planning-rules__toggle-copy"><b>Mehrere Schichten pro Tag</b><span>Mehr als einen Einsatz pro Mitarbeiter und Kalendertag erlauben.</span></div>
              <IonToggle checked={!!policy.allow_multiple_shifts_per_day} onIonChange={e=>setPolicy({...policy,allow_multiple_shifts_per_day:e.detail.checked})} aria-label="Mehrere Schichten pro Tag"/>
            </div>
            <div className="admin-planning-rules__toggle">
              <div className="admin-planning-rules__toggle-copy"><b>Monatliche Sollstunden berücksichtigen</b><span>Zuweisungen gegen die hinterlegten Monatsstunden des Mitarbeiters prüfen.</span></div>
              <IonToggle checked={!!policy.respect_worker_monthly_hours} onIonChange={e=>setPolicy({...policy,respect_worker_monthly_hours:e.detail.checked})} aria-label="Monatliche Sollstunden berücksichtigen"/>
            </div>
            <div className="admin-planning-rules__toggle">
              <div className="admin-planning-rules__toggle-copy"><b>Überlappende OpenShifts zulassen</b><span>Offene Bedarfe dürfen zeitlich parallel bestehen; belegte Schichten bleiben kollisionsgeprüft.</span></div>
              <IonToggle checked={!!policy.allow_overlapping_open_shifts} onIonChange={e=>setPolicy({...policy,allow_overlapping_open_shifts:e.detail.checked})} aria-label="Überlappende OpenShifts zulassen"/>
            </div>
          </div>
          <div className="admin-planning-rules__note"><strong>Hinweis:</strong><span>Die 11-Stunden-Regel, die bei Francesco gegriffen hat, ist hier als „Ruhezeit zwischen Arbeitstagen“ sichtbar und kann zentral angepasst werden.</span></div>
        </div>
      </div>
    </section>}

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

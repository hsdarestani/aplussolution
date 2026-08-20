import React, { useEffect, useMemo, useState } from 'react';
import {
  IonAlert,
  IonBadge,
  IonButton,
  IonIcon,
  IonInput,
  IonItem,
  IonLabel,
  IonModal,
  IonSearchbar,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonToast,
  IonToggle,
} from '@ionic/react';
import {
  briefcaseOutline,
  checkmarkCircleOutline,
  closeCircleOutline,
  copyOutline,
  createOutline,
  locationOutline,
  mailOutline,
  personAddOutline,
  refreshOutline,
} from 'ionicons/icons';
import { api } from './api';
import './employee-portal.css';
import './masterdata-quick.css';

const label:any={active:'Aktiv',invited:'Einladung offen',not_activated:'Nicht aktiviert',missing_email:'E-Mail fehlt'};
const color:any={active:'success',invited:'primary',not_activated:'warning',missing_email:'danger'};
const isSyntheticMigrationRow=(row:any)=>String(row?.email||'').toLowerCase().endsWith('@sync.invalid');
const unpack=(data:any):any[]=>data?.results||data||[];
const value=(event:any)=>event.detail.value??'';

function MasterDataQuickPanel(){
  const [clients,setClients]=useState<any[]>([]);
  const [locations,setLocations]=useState<any[]>([]);
  const [positions,setPositions]=useState<any[]>([]);
  const [modal,setModal]=useState<'location'|'position'|''>('');
  const [editing,setEditing]=useState<any>();
  const [locationForm,setLocationForm]=useState<any>({geofence_radius_m:250,active:true});
  const [positionForm,setPositionForm]=useState<any>({color:'#155eef',active:true});
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [toast,setToast]=useState('');

  async function load(){
    setLoading(true);
    try{
      const [clientData,locationData,positionData]=await Promise.all([
        api('clients/?ordering=name'),
        api('locations/'),
        api('positions/'),
      ]);
      setClients(unpack(clientData));
      setLocations(unpack(locationData));
      setPositions(unpack(positionData));
    }catch(error:any){
      setToast(error.message);
    }finally{
      setLoading(false);
    }
  }

  useEffect(()=>{void load();},[]);

  function openLocation(item?:any){
    setEditing(item);
    setLocationForm(item?{
      client:item.client||'',
      name:item.name||'',
      address:item.address||'',
      geofence_radius_m:item.geofence_radius_m||250,
      active:item.active!==false,
    }:{geofence_radius_m:250,active:true});
    setModal('location');
  }

  function openPosition(item?:any){
    setEditing(item);
    setPositionForm(item?{
      name:item.name||'',
      color:item.color||'#155eef',
      active:item.active!==false,
    }:{color:'#155eef',active:true});
    setModal('position');
  }

  async function saveLocation(){
    if(!String(locationForm.name||'').trim()||!String(locationForm.address||'').trim()){
      setToast('Bitte Bezeichnung und Adresse ausfüllen.');
      return;
    }
    setBusy(true);
    try{
      const payload={
        ...locationForm,
        client:locationForm.client||null,
        geofence_radius_m:Number(locationForm.geofence_radius_m||250),
      };
      await api(editing?`locations/${editing.id}/`:'locations/',{
        method:editing?'PATCH':'POST',
        body:JSON.stringify(payload),
      });
      setToast(editing?'Einsatzort wurde aktualisiert.':'Einsatzort wurde angelegt.');
      setModal('');
      setEditing(undefined);
      await load();
    }catch(error:any){
      setToast(error.message);
    }finally{
      setBusy(false);
    }
  }

  async function savePosition(){
    if(!String(positionForm.name||'').trim()){
      setToast('Bitte eine Bezeichnung eingeben.');
      return;
    }
    setBusy(true);
    try{
      await api(editing?`positions/${editing.id}/`:'positions/',{
        method:editing?'PATCH':'POST',
        body:JSON.stringify(positionForm),
      });
      setToast(editing?'Position wurde aktualisiert.':'Position wurde angelegt.');
      setModal('');
      setEditing(undefined);
      await load();
    }catch(error:any){
      setToast(error.message);
    }finally{
      setBusy(false);
    }
  }

  async function toggle(kind:'locations'|'positions',item:any){
    setBusy(true);
    try{
      await api(`${kind}/${item.id}/`,{
        method:'PATCH',
        body:JSON.stringify({active:item.active===false}),
      });
      setToast(item.active===false?'Stammdatensatz wurde aktiviert.':'Stammdatensatz wurde deaktiviert.');
      await load();
    }catch(error:any){
      setToast(error.message);
    }finally{
      setBusy(false);
    }
  }

  return <>
    <section className="masterdata-quick-panel" data-testid="masterdata-quick-panel">
      <div className="masterdata-quick-head">
        <div>
          <small>STAMMDATEN</small>
          <h2>Einsatzorte & Positionen</h2>
          <p>Direkt hier anlegen und bearbeiten – diese Daten stehen danach sofort in Dienstplanung und Aufträgen bereit.</p>
        </div>
        <IonButton fill="clear" disabled={loading||busy} onClick={()=>void load()} aria-label="Stammdaten aktualisieren"><IonIcon slot="icon-only" icon={refreshOutline}/></IonButton>
      </div>

      <div className="masterdata-create-actions">
        <IonButton onClick={()=>openLocation()}><IonIcon slot="start" icon={locationOutline}/>Einsatzort anlegen</IonButton>
        <IonButton fill="outline" onClick={()=>openPosition()}><IonIcon slot="start" icon={briefcaseOutline}/>Position anlegen</IonButton>
      </div>

      {loading?<div className="masterdata-loading"><IonSpinner/><span>Stammdaten werden geladen …</span></div>:<div className="masterdata-quick-grid">
        <div className="masterdata-card">
          <div className="masterdata-card-title"><div><IonIcon icon={locationOutline}/><div><b>Einsatzorte</b><span>{locations.filter(item=>item.active!==false).length} aktiv · {locations.length} gesamt</span></div></div></div>
          <div className="masterdata-list">
            {locations.slice(0,6).map(item=><div className={`masterdata-row ${item.active===false?'inactive':''}`} key={item.id}>
              <div className="masterdata-main"><b>{item.name}</b><span>{item.client_name||'Ohne Kunde'} · {item.address}</span></div>
              <IonBadge color={item.active===false?'medium':'success'}>{item.active===false?'Inaktiv':'Aktiv'}</IonBadge>
              <div className="masterdata-row-actions">
                <IonButton size="small" fill="clear" onClick={()=>openLocation(item)} aria-label={`${item.name} bearbeiten`}><IonIcon slot="icon-only" icon={createOutline}/></IonButton>
                <IonButton size="small" fill="clear" color={item.active===false?'success':'medium'} disabled={busy} onClick={()=>void toggle('locations',item)} aria-label={`${item.name} ${item.active===false?'aktivieren':'deaktivieren'}`}><IonIcon slot="icon-only" icon={item.active===false?checkmarkCircleOutline:closeCircleOutline}/></IonButton>
              </div>
            </div>)}
            {!locations.length&&<div className="masterdata-empty">Noch keine Einsatzorte. Lege den ersten Einsatzort oben an.</div>}
            {locations.length>6&&<div className="masterdata-more">+ {locations.length-6} weitere Einsatzorte weiter unten auf dieser Seite</div>}
          </div>
        </div>

        <div className="masterdata-card">
          <div className="masterdata-card-title"><div><IonIcon icon={briefcaseOutline}/><div><b>Positionen</b><span>{positions.filter(item=>item.active!==false).length} aktiv · {positions.length} gesamt</span></div></div></div>
          <div className="masterdata-list">
            {positions.slice(0,6).map(item=><div className={`masterdata-row ${item.active===false?'inactive':''}`} key={item.id}>
              <div className="masterdata-main position"><i style={{background:item.color||'#155eef'}}/><b>{item.name}</b></div>
              <IonBadge color={item.active===false?'medium':'success'}>{item.active===false?'Inaktiv':'Aktiv'}</IonBadge>
              <div className="masterdata-row-actions">
                <IonButton size="small" fill="clear" onClick={()=>openPosition(item)} aria-label={`${item.name} bearbeiten`}><IonIcon slot="icon-only" icon={createOutline}/></IonButton>
                <IonButton size="small" fill="clear" color={item.active===false?'success':'medium'} disabled={busy} onClick={()=>void toggle('positions',item)} aria-label={`${item.name} ${item.active===false?'aktivieren':'deaktivieren'}`}><IonIcon slot="icon-only" icon={item.active===false?checkmarkCircleOutline:closeCircleOutline}/></IonButton>
              </div>
            </div>)}
            {!positions.length&&<div className="masterdata-empty">Noch keine Positionen. Lege die erste Position oben an.</div>}
            {positions.length>6&&<div className="masterdata-more">+ {positions.length-6} weitere Positionen weiter unten auf dieser Seite</div>}
          </div>
        </div>
      </div>}
    </section>

    <IonModal isOpen={modal==='location'} onDidDismiss={()=>{setModal('');setEditing(undefined);}}>
      <div className="masterdata-modal">
        <div className="masterdata-modal-head"><div><small>STAMMDATEN</small><h2>{editing?'Einsatzort bearbeiten':'Einsatzort anlegen'}</h2></div><IonButton fill="clear" onClick={()=>{setModal('');setEditing(undefined);}}>Schließen</IonButton></div>
        <div className="masterdata-form">
          <IonSelect fill="outline" label="Kunde" labelPlacement="floating" value={locationForm.client||''} onIonChange={event=>setLocationForm({...locationForm,client:value(event)})}>
            <IonSelectOption value="">Ohne feste Zuordnung</IonSelectOption>
            {clients.filter(client=>client.active!==false).map(client=><IonSelectOption value={client.id} key={client.id}>{client.name}</IonSelectOption>)}
          </IonSelect>
          <IonInput fill="outline" label="Bezeichnung *" labelPlacement="floating" value={locationForm.name||''} onIonInput={event=>setLocationForm({...locationForm,name:value(event)})}/>
          <IonTextarea className="full" fill="outline" label="Adresse *" labelPlacement="floating" value={locationForm.address||''} onIonInput={event=>setLocationForm({...locationForm,address:value(event)})}/>
          <IonInput fill="outline" type="number" min="1" label="Geofence-Radius (m)" labelPlacement="floating" value={locationForm.geofence_radius_m||250} onIonInput={event=>setLocationForm({...locationForm,geofence_radius_m:value(event)})}/>
          <IonItem lines="none" className="masterdata-toggle"><IonLabel>Aktiv</IonLabel><IonToggle checked={locationForm.active!==false} onIonChange={event=>setLocationForm({...locationForm,active:event.detail.checked})}/></IonItem>
        </div>
        <div className="masterdata-modal-actions"><IonButton fill="outline" onClick={()=>{setModal('');setEditing(undefined);}}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>void saveLocation()}>{busy?<IonSpinner name="dots"/>:'Speichern'}</IonButton></div>
      </div>
    </IonModal>

    <IonModal isOpen={modal==='position'} onDidDismiss={()=>{setModal('');setEditing(undefined);}}>
      <div className="masterdata-modal compact">
        <div className="masterdata-modal-head"><div><small>STAMMDATEN</small><h2>{editing?'Position bearbeiten':'Position anlegen'}</h2></div><IonButton fill="clear" onClick={()=>{setModal('');setEditing(undefined);}}>Schließen</IonButton></div>
        <div className="masterdata-form one-column">
          <IonInput fill="outline" label="Bezeichnung *" labelPlacement="floating" value={positionForm.name||''} onIonInput={event=>setPositionForm({...positionForm,name:value(event)})}/>
          <IonInput fill="outline" label="Farbe (HEX)" labelPlacement="floating" placeholder="#155eef" value={positionForm.color||'#155eef'} onIonInput={event=>setPositionForm({...positionForm,color:value(event)})}/>
          <IonItem lines="none" className="masterdata-toggle"><IonLabel>Aktiv</IonLabel><IonToggle checked={positionForm.active!==false} onIonChange={event=>setPositionForm({...positionForm,active:event.detail.checked})}/></IonItem>
        </div>
        <div className="masterdata-modal-actions"><IonButton fill="outline" onClick={()=>{setModal('');setEditing(undefined);}}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>void savePosition()}>{busy?<IonSpinner name="dots"/>:'Speichern'}</IonButton></div>
      </div>
    </IonModal>

    <IonToast isOpen={!!toast} message={toast} duration={4000} onDidDismiss={()=>setToast('')}/>
  </>;
}

export default function PortalAccessPanel(){
  const [rows,setRows]=useState<any[]>([]),[search,setSearch]=useState(''),[toast,setToast]=useState(''),[busy,setBusy]=useState(''),[confirmBulk,setConfirmBulk]=useState(false);
  async function load(){const result:any[]=await api(`workers/portal-status/?search=${encodeURIComponent(search)}`);setRows((result||[]).filter(row=>!isSyntheticMigrationRow(row)));}
  useEffect(()=>{void load();},[]);
  const counts=useMemo(()=>rows.reduce((a:any,x:any)=>{a[x.state]=(a[x.state]||0)+1;return a;},{}),[rows]);
  const bulkRows=useMemo(()=>rows.filter((row:any)=>row.state!=='active'&&row.state!=='missing_email'),[rows]);
  const bulkEligible=bulkRows.length;
  async function invite(row:any){setBusy(row.worker_id);try{const r:any=await api(`workers/${row.worker_id}/invite/`,{method:'POST',body:'{}'});if(r.activation_url){await navigator.clipboard?.writeText(r.activation_url);setToast('Aktivierungslink wurde erstellt und in die Zwischenablage kopiert.');}else setToast('Einladung wurde per E-Mail versendet.');await load();}catch(e:any){setToast(e.message);}finally{setBusy('');}}
  async function bulk(){const workerIds=bulkRows.map((row:any)=>row.worker_id).filter(Boolean);if(!workerIds.length)return;setBusy('bulk');try{const r:any=await api('workers/bulk-invite/',{method:'POST',body:JSON.stringify({worker_ids:workerIds})});const links=(r.results||[]).filter((x:any)=>x.activation_url&&!String(x.email||'').toLowerCase().endsWith('@sync.invalid')).map((x:any)=>`${x.email}: ${x.activation_url}`).join('\n');if(links){await navigator.clipboard?.writeText(links);setToast(`${r.count} Einladung(en) erstellt. Links wurden kopiert.`);}else setToast(`${r.count} Einladung(en) verarbeitet.`);await load();}catch(e:any){setToast(e.message);}finally{setBusy('');}}
  return <>
    <MasterDataQuickPanel/>
    <section className="portal-access-panel">
      <div className="portal-access-head"><div><small>MITARBEITERPORTAL</small><h2>Zugänge & Aktivierung</h2><p>Mitarbeiter aktivieren ihren eigenen A+ Workforce Zugang. Keine Passwörter werden von der Disposition vergeben.</p></div><IonButton fill="outline" disabled={!!busy||bulkEligible===0} onClick={()=>setConfirmBulk(true)}><IonIcon slot="start" icon={personAddOutline}/>Offene Einladungen erstellen</IonButton></div>
      <div className="portal-access-stats"><span><b>{counts.active||0}</b> aktiv</span><span><b>{counts.invited||0}</b> eingeladen</span><span><b>{counts.not_activated||0}</b> nicht aktiviert</span><span><b>{counts.missing_email||0}</b> ohne E-Mail</span></div>
      <div className="portal-search"><IonSearchbar value={search} debounce={350} placeholder="Mitarbeiter, E-Mail oder Personalnummer suchen …" onIonInput={e=>setSearch(String(e.detail.value||''))} onIonChange={()=>void load()}/><IonButton fill="clear" onClick={()=>void load()}><IonIcon slot="icon-only" icon={refreshOutline}/></IonButton></div>
      <div className="portal-access-list">{rows.map(row=><div className="portal-access-row" key={row.worker_id}><div className="portal-person"><span>{String(row.name||'M')[0].toUpperCase()}</span><div><b>{row.name}</b><p>{row.email}</p></div></div><IonBadge color={color[row.state]||'medium'}>{label[row.state]||row.state}</IonBadge>{row.state!=='active'&&row.state!=='missing_email'&&<IonButton size="small" fill="outline" disabled={!!busy} onClick={()=>invite(row)}><IonIcon slot="start" icon={row.state==='invited'?copyOutline:mailOutline}/>{row.state==='invited'?'Neu senden':'Einladen'}</IonButton>}</div>)}</div>
      <IonAlert
        isOpen={confirmBulk}
        onDidDismiss={()=>setConfirmBulk(false)}
        header="Offene Einladungen wirklich erstellen?"
        message={`Für ${bulkEligible} aktuell angezeigte Mitarbeiter werden Aktivierungen verarbeitet. Bereits aktive Zugänge, fehlende E-Mail-Adressen und Migrationsdatensätze bleiben unberührt.`}
        buttons={[
          {text:'Abbrechen',role:'cancel'},
          {text:'Einladungen erstellen',handler:()=>{setConfirmBulk(false);void bulk();}},
        ]}
      />
      <IonToast isOpen={!!toast} message={toast} duration={4500} onDidDismiss={()=>setToast('')}/>
    </section>
  </>;
}

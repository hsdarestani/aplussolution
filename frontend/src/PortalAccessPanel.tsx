import React, { useEffect, useMemo, useState } from 'react';
import { IonAlert, IonBadge, IonButton, IonIcon, IonSearchbar, IonToast } from '@ionic/react';
import { copyOutline, mailOutline, personAddOutline, refreshOutline } from 'ionicons/icons';
import { api } from './api';
import './employee-portal.css';

const label:any={active:'Aktiv',invited:'Einladung offen',not_activated:'Nicht aktiviert',missing_email:'E-Mail fehlt'};
const color:any={active:'success',invited:'primary',not_activated:'warning',missing_email:'danger'};
const isSyntheticMigrationRow=(row:any)=>String(row?.email||'').toLowerCase().endsWith('@sync.invalid');

export default function PortalAccessPanel(){
  const [rows,setRows]=useState<any[]>([]),[search,setSearch]=useState(''),[toast,setToast]=useState(''),[busy,setBusy]=useState(''),[confirmBulk,setConfirmBulk]=useState(false);
  async function load(){const result:any[]=await api(`workers/portal-status/?search=${encodeURIComponent(search)}`);setRows((result||[]).filter(row=>!isSyntheticMigrationRow(row)));}
  useEffect(()=>{void load();},[]);
  const counts=useMemo(()=>rows.reduce((a:any,x:any)=>{a[x.state]=(a[x.state]||0)+1;return a;},{}),[rows]);
  const bulkRows=useMemo(()=>rows.filter((row:any)=>row.state!=='active'&&row.state!=='missing_email'),[rows]);
  const bulkEligible=bulkRows.length;
  async function invite(row:any){setBusy(row.worker_id);try{const r:any=await api(`workers/${row.worker_id}/invite/`,{method:'POST',body:'{}'});if(r.activation_url){await navigator.clipboard?.writeText(r.activation_url);setToast('Aktivierungslink wurde erstellt und in die Zwischenablage kopiert.');}else setToast('Einladung wurde per E-Mail versendet.');await load();}catch(e:any){setToast(e.message);}finally{setBusy('');}}
  async function bulk(){const workerIds=bulkRows.map((row:any)=>row.worker_id).filter(Boolean);if(!workerIds.length)return;setBusy('bulk');try{const r:any=await api('workers/bulk-invite/',{method:'POST',body:JSON.stringify({worker_ids:workerIds})});const links=(r.results||[]).filter((x:any)=>x.activation_url&&!String(x.email||'').toLowerCase().endsWith('@sync.invalid')).map((x:any)=>`${x.email}: ${x.activation_url}`).join('\n');if(links){await navigator.clipboard?.writeText(links);setToast(`${r.count} Einladung(en) erstellt. Links wurden kopiert.`);}else setToast(`${r.count} Einladung(en) verarbeitet.`);await load();}catch(e:any){setToast(e.message);}finally{setBusy('');}}
  return <section className="portal-access-panel">
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
  </section>;
}

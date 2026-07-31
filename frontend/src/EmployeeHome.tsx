import React, { useEffect, useState } from 'react';
import { IonBadge, IonButton, IonIcon, IonSpinner } from '@ionic/react';
import { calendarOutline, chevronForwardOutline, documentTextOutline, notificationsOutline, stopwatchOutline } from 'ionicons/icons';
import { api, User } from './api';
import './employee-portal.css';

const time = (x:string) => new Date(x).toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
const day = (x:string) => new Date(x).toLocaleDateString('de-DE',{weekday:'short',day:'2-digit',month:'short'});

export default function EmployeeHome({user,navigate}:{user:User;navigate:(view:any)=>void}) {
  const [data,setData]=useState<any>();
  const [error,setError]=useState('');
  useEffect(()=>{api('employee/home/').then(setData).catch(e=>setError(e.message));},[]);
  if(error) return <div className="employee-empty"><h2>Startseite konnte nicht geladen werden</h2><p>{error}</p></div>;
  if(!data) return <div className="employee-loader"><IonSpinner/><span>Dein Bereich wird geladen …</span></div>;
  const worked = Number(data.month_worked_minutes||0);
  return <div className="employee-home">
    <header className="employee-welcome"><div><small>GUTEN TAG</small><h1>{data.worker?.name || user.name}</h1><p>{data.worker?.employee_number} · {data.worker?.employment_type}</p></div><button onClick={()=>navigate('messages')}><IonIcon icon={notificationsOutline}/>{data.unread_notifications>0&&<b>{data.unread_notifications}</b>}</button></header>

    {data.next_shift ? <section className="next-shift-card" onClick={()=>navigate('schedule')}>
      <div className="next-shift-label"><span>NÄCHSTER EINSATZ</span><IonBadge color="light">Bestätigt</IonBadge></div>
      <h2>{data.next_shift.position_name}</h2>
      <p>{data.next_shift.client_name} · {data.next_shift.location_name}</p>
      <div className="next-shift-time"><strong>{day(data.next_shift.starts_at)}</strong><span>{time(data.next_shift.starts_at)}–{time(data.next_shift.ends_at)}</span></div>
      <IonIcon className="next-arrow" icon={chevronForwardOutline}/>
    </section> : <section className="next-shift-card empty"><small>DEIN NÄCHSTER EINSATZ</small><h2>Noch nichts geplant</h2><p>Schau dir verfügbare Schichten an und wähle den nächsten passenden Einsatz.</p><IonButton color="light" onClick={(e)=>{e.stopPropagation();navigate('schedule')}}>Schichten ansehen</IonButton></section>}

    <div className="employee-kpis">
      <button onClick={()=>navigate('schedule')}><IonIcon icon={calendarOutline}/><b>{data.available_count||0}</b><span>freie Schichten</span></button>
      <button onClick={()=>navigate('time')}><IonIcon icon={stopwatchOutline}/><b>{Math.floor(worked/60)}:{String(worked%60).padStart(2,'0')}</b><span>Std. diesen Monat</span></button>
      <button onClick={()=>navigate('contracts')}><IonIcon icon={documentTextOutline}/><b>{data.contract_actions||0}</b><span>Verträge offen</span></button>
    </div>

    <section className="employee-section">
      <div className="employee-section-head"><div><small>OPENSHIFTS</small><h2>Für dich verfügbar</h2></div><button onClick={()=>navigate('schedule')}>Alle ansehen</button></div>
      <div className="available-strip">{data.available_shifts?.map((shift:any)=><button className="available-mini" key={shift.id} onClick={()=>navigate('schedule')}><span>{day(shift.starts_at)}</span><strong>{shift.position_name}</strong><p>{time(shift.starts_at)} · {shift.location_name}</p><b>{shift.open_count} frei</b></button>)}{!data.available_shifts?.length&&<div className="employee-inline-empty">Aktuell keine freien Schichten.</div>}</div>
    </section>

    <section className="employee-section compact">
      <div className="employee-section-head"><div><small>AKTIONEN</small><h2>Was deine Aufmerksamkeit braucht</h2></div></div>
      <button className="employee-action-row" onClick={()=>navigate('contracts')}><span><IonIcon icon={documentTextOutline}/></span><div><b>Verträge & Dokumente</b><p>{data.contract_actions||0} benötigen eine Aktion · {data.contracts_expiring_30||0} laufen bald aus</p></div><IonIcon icon={chevronForwardOutline}/></button>
      <button className="employee-action-row" onClick={()=>navigate('messages')}><span><IonIcon icon={notificationsOutline}/></span><div><b>Benachrichtigungen</b><p>{data.unread_notifications||0} ungelesene Hinweise</p></div><IonIcon icon={chevronForwardOutline}/></button>
    </section>
  </div>;
}

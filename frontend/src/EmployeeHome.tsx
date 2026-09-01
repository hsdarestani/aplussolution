import React, { useEffect, useState } from 'react';
import { IonBadge, IonButton, IonIcon, IonSpinner } from '@ionic/react';
import {
  calendarOutline,
  chevronForwardOutline,
  documentTextOutline,
  locationOutline,
  notificationsOutline,
  peopleOutline,
  stopwatchOutline,
} from 'ionicons/icons';
import { api, User } from './api';
import './employee-portal.css';
import './wiw-employee-home-mobile.css';

const APP_TIME_ZONE = 'Europe/Berlin';
const time = (x:string) => new Date(x).toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit',timeZone:APP_TIME_ZONE});
const day = (x:string) => new Date(x).toLocaleDateString('de-DE',{weekday:'short',day:'2-digit',month:'short',timeZone:APP_TIME_ZONE});

function MobileRow({icon,label,count,onClick,muted}:{icon:string;label:string;count?:number|string;onClick:()=>void;muted?:boolean}) {
  return <button type="button" className={`wiw-mobile-row ${muted?'muted':''}`} onClick={onClick}>
    {count!==undefined?<span className="wiw-count">{count}</span>:<span className="wiw-row-icon"><IonIcon icon={icon}/></span>}
    <strong>{label}</strong>
    <IonIcon className="wiw-row-chevron" icon={chevronForwardOutline}/>
  </button>;
}

async function currentPosition(): Promise<GeolocationPosition> {
  if (!navigator.geolocation) throw new Error('Standortdienste werden auf diesem Gerät nicht unterstützt.');
  return new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(
    resolve,
    (error) => {
      if (error.code === error.PERMISSION_DENIED) reject(new Error('Standortzugriff wurde nicht erlaubt. Bitte Standortdienste aktivieren.'));
      else if (error.code === error.TIMEOUT) reject(new Error('Standort konnte nicht rechtzeitig bestimmt werden. Bitte erneut versuchen.'));
      else reject(new Error('Standort konnte nicht bestimmt werden.'));
    },
    { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 },
  ));
}

export default function EmployeeHome({user,navigate}:{user:User;navigate:(view:any)=>void}) {
  const [data,setData]=useState<any>();
  const [attendance,setAttendance]=useState<any>();
  const [error,setError]=useState('');
  const [clockIntent,setClockIntent]=useState<'in'|'out'|''>('');
  const [clockBusy,setClockBusy]=useState(false);
  const [notice,setNotice]=useState('');

  const load = async () => {
    try {
      const [home, attendanceHome] = await Promise.all([api('employee/home/'), api('attendance/home/')]);
      setData(home);
      setAttendance(attendanceHome);
      setError('');
    } catch (e:any) {
      setError(e.message);
    }
  };

  useEffect(()=>{void load();},[]);

  async function clock() {
    if (!clockIntent) return;
    setClockBusy(true);
    setNotice('');
    try {
      const position = await currentPosition();
      const payload:any = { lat: position.coords.latitude, lng: position.coords.longitude };
      if (clockIntent === 'in' && attendance?.eligible_shift?.id) payload.shift = attendance.eligible_shift.id;
      const result:any = await api(`time-entries/clock_${clockIntent}/`, { method: 'POST', body: JSON.stringify(payload) });
      setNotice(clockIntent === 'in'
        ? 'Du bist eingestempelt.'
        : result?.review_required ? 'Ausgestempelt. Der Standort wird von der Administration geprüft.' : 'Du bist ausgestempelt.');
      setClockIntent('');
      await load();
    } catch (e:any) {
      setNotice(e.message || 'Zeiterfassung konnte nicht gestartet werden.');
    } finally {
      setClockBusy(false);
    }
  }

  if(error) return <div className="employee-empty"><h2>Startseite konnte nicht geladen werden</h2><p>{error}</p></div>;
  if(!data||!attendance) return <div className="employee-loader"><IonSpinner/><span>Dein Bereich wird geladen …</span></div>;
  const worked = Number(data.month_worked_minutes||0);
  const nextShift = data.next_shift;
  const active = attendance.active_entry;
  const canClockIn = Boolean(attendance.eligible_shift?.id);

  return <>
    <div className="wiw-mobile-dashboard wiw-worker-home" data-testid="phase8-mobile-dashboard">
      <div className="wiw-section-label">Anfragen</div>
      <MobileRow icon={calendarOutline} label="Schichtanfragen" count={0} onClick={()=>navigate('operations')}/>
      <MobileRow icon={calendarOutline} label="OpenShift-Anfragen" count={data.open_shift_requests||0} onClick={()=>{sessionStorage.setItem('aplus:schedule-entry-filter','open');navigate('schedule');}}/>

      <div className="wiw-section-label">Mein Zeitplan</div>
      <button type="button" className="wiw-next-shift wiw-worker-next" onClick={()=>navigate('schedule')}>
        <small>{nextShift ? `Nächste Schicht: ${day(nextShift.starts_at)}` : 'Nächste Schicht'}</small>
        <strong>{nextShift ? `${time(nextShift.starts_at)}–${time(nextShift.ends_at)}` : 'Keine anstehende Schicht'}</strong>
        {nextShift&&<>
          <span className="wiw-next-meta">⌁ {nextShift.client_name || 'A+'}</span>
          <span className="wiw-next-meta">⌖ {nextShift.location_name}</span>
          <span className="wiw-next-meta">♙ {nextShift.position_name}</span>
        </>}
        <IonIcon className="wiw-next-chevron" icon={chevronForwardOutline}/>
      </button>
      <MobileRow icon={calendarOutline} label="Meine Schichten" onClick={()=>navigate('schedule')}/>
      <MobileRow icon={calendarOutline} label="OpenShifts verfügbar" count={data.available_count||0} onClick={()=>{sessionStorage.setItem('aplus:schedule-entry-filter','open');navigate('schedule');}}/>

      <div className="wiw-section-label">Zeiterfassung</div>
      <div className="wiw-home-clock-card">
        <div className="wiw-home-clock-copy">
          <span className="wiw-home-clock-icon"><IonIcon icon={locationOutline}/></span>
          <div>
            <b>{active ? 'Arbeitszeit läuft' : canClockIn ? 'Bereit zum Einstempeln' : 'Noch keine Zeiterfassung möglich'}</b>
            <small>{active ? `Seit ${time(active.clock_in)}` : canClockIn ? `${attendance.eligible_shift.position_name || 'Einsatz'} · ${attendance.eligible_shift.location_name}` : 'Einstempeln ist rund um eine bestätigte Schicht möglich.'}</small>
          </div>
        </div>
        <button type="button" className={active ? 'clock-out' : ''} disabled={clockBusy || (!active && !canClockIn)} onClick={()=>setClockIntent(active?'out':'in')}>
          {active ? 'Ausstempeln' : 'Einstempeln'}
        </button>
      </div>

      <div className="wiw-section-label">Wichtige bevorstehende Daten</div>
      <div className="wiw-upcoming wiw-worker-upcoming">
        {nextShift?<div><strong>{nextShift.position_name}</strong><span>{nextShift.client_name} · {day(nextShift.starts_at)} {time(nextShift.starts_at)}</span></div>:<span>Keine wichtigen anstehenden Termine</span>}
      </div>
      {notice&&<div className="wiw-home-notice">{notice}</div>}
    </div>

    <div className="employee-desktop-dashboard">
      <div className="employee-home">
        <header className="employee-welcome"><div><small>GUTEN TAG</small><h1>{data.worker?.name || user.name}</h1><p>{data.worker?.employee_number} · {data.worker?.employment_type}</p></div><button onClick={()=>navigate('messages')}><IonIcon icon={notificationsOutline}/>{data.unread_notifications>0&&<b>{data.unread_notifications}</b>}</button></header>

        {nextShift ? <section className="next-shift-card" onClick={()=>navigate('schedule')}>
          <div className="next-shift-label"><span>NÄCHSTER EINSATZ</span><IonBadge color="light">Bestätigt</IonBadge></div>
          <h2>{nextShift.position_name}</h2>
          <p>{nextShift.client_name} · {nextShift.location_name}</p>
          <div className="next-shift-time"><strong>{day(nextShift.starts_at)}</strong><span>{time(nextShift.starts_at)}–{time(nextShift.ends_at)}</span></div>
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
      </div>
    </div>

    {clockIntent&&<div className="wiw-location-backdrop" role="dialog" aria-modal="true" aria-label="Standortberechtigung">
      <div className="wiw-location-modal">
        <div className="wiw-location-symbol"><IonIcon icon={locationOutline}/></div>
        <h2>Für die Zeiterfassung ist eine Berechtigung zur Standortbestimmung erforderlich</h2>
        <p>Aktiviere die Standortdienste, damit A+ weiß, wo du deine Arbeitszeit {clockIntent==='in'?'beginnst':'beendest'}.</p>
        {notice&&<div className="wiw-location-error">{notice}</div>}
        <button type="button" className="activate" disabled={clockBusy} onClick={()=>void clock()}>{clockBusy?'Standort wird bestimmt …':'Standortdienste aktivieren'}</button>
        <button type="button" className="cancel" disabled={clockBusy} onClick={()=>{setClockIntent('');setNotice('');}}>Abbrechen</button>
      </div>
    </div>}
  </>;
}

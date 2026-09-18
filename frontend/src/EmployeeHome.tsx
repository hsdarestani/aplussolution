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
import { api, clockLocationRequired, User } from './api';
import GermanTimeField from './GermanTimeField';
import TimeReportLegalConfirmation from './TimeReportLegalConfirmation';
import './employee-portal.css';
import './wiw-employee-home-mobile.css';

const APP_TIME_ZONE = 'Europe/Berlin';
const time = (x:string) => new Date(x).toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit',timeZone:APP_TIME_ZONE});
const day = (x:string) => new Date(x).toLocaleDateString('de-DE',{weekday:'short',day:'2-digit',month:'short',timeZone:APP_TIME_ZONE});
const inputTime = (x:string) => new Date(x).toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:APP_TIME_ZONE});
const dateKey = (x:string) => {
  const parts = new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:APP_TIME_ZONE}).formatToParts(new Date(x));
  const pick = (type:string) => parts.find((part)=>part.type===type)?.value || '';
  return `${pick('year')}-${pick('month')}-${pick('day')}`;
};
const nextDateKey = (value:string) => {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate()+1);
  return date.toISOString().slice(0,10);
};

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
  const [timeReport,setTimeReport]=useState<any>();
  const [timeReportBusy,setTimeReportBusy]=useState(false);
  const [timeReportLegalOpen,setTimeReportLegalOpen]=useState(false);

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

  useEffect(()=>{
    const shift = attendance?.pending_shift_report;
    if (!shift?.id || timeReport) return;
    if (sessionStorage.getItem(`aplus:time-report-later:${shift.id}`) === '1') return;
    setTimeReport({
      shift,
      date: dateKey(shift.starts_at),
      clock_in: inputTime(shift.starts_at),
      clock_out: inputTime(shift.ends_at),
    });
  },[attendance?.pending_shift_report?.id]);

  function requestTimeReportSubmit() {
    if (!timeReport?.shift?.id || !timeReport.clock_in || !timeReport.clock_out) {
      setNotice('Bitte Beginn und Ende vollständig angeben.');
      return;
    }
    setNotice('');
    setTimeReportLegalOpen(true);
  }

  async function submitTimeReport() {
    if (!timeReport?.shift?.id || !timeReport.clock_in || !timeReport.clock_out) return;
    setTimeReportBusy(true);
    setNotice('');
    try {
      const endDate = timeReport.clock_out <= timeReport.clock_in ? nextDateKey(timeReport.date) : timeReport.date;
      await api('time-entries/report_shift/', {
        method: 'POST',
        body: JSON.stringify({
          shift: timeReport.shift.id,
          clock_in: `${timeReport.date}T${timeReport.clock_in}:00`,
          clock_out: `${endDate}T${timeReport.clock_out}:00`,
          legal_acknowledged: true,
        }),
      });
      sessionStorage.removeItem(`aplus:time-report-later:${timeReport.shift.id}`);
      setTimeReportLegalOpen(false);
      setTimeReport(undefined);
      setNotice('Arbeitszeit wurde zur Freigabe an die Administration gesendet.');
      await load();
    } catch (e:any) {
      setNotice(e.message || 'Arbeitszeit konnte nicht gesendet werden.');
    } finally {
      setTimeReportBusy(false);
    }
  }

  function postponeTimeReport() {
    if (timeReport?.shift?.id) sessionStorage.setItem(`aplus:time-report-later:${timeReport.shift.id}`, '1');
    setTimeReportLegalOpen(false);
    setTimeReport(undefined);
  }

  async function clock(intent: 'in'|'out', requireLocation: boolean) {
    setClockBusy(true);
    setNotice('');
    try {
      const payload:any = {};
      if (requireLocation) {
        const position = await currentPosition();
        payload.lat = position.coords.latitude;
        payload.lng = position.coords.longitude;
      } else {
        payload.skip_location = true;
      }
      if (intent === 'in' && attendance?.eligible_shift?.id) payload.shift = attendance.eligible_shift.id;
      const result:any = await api(`time-entries/clock_${intent}/`, { method: 'POST', body: JSON.stringify(payload) });
      setNotice(intent === 'in'
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

  async function beginClock(intent: 'in'|'out') {
    setClockBusy(true);
    setNotice('');
    try {
      const shiftId = intent === 'in' ? attendance?.eligible_shift?.id : attendance?.active_entry?.shift;
      const requireLocation = await clockLocationRequired(shiftId);
      if (requireLocation) {
        setClockIntent(intent);
        return;
      }
      await clock(intent, false);
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
        <button type="button" className={active ? 'clock-out' : ''} disabled={clockBusy || (!active && !canClockIn)} onClick={()=>void beginClock(active?'out':'in')}>
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

    {timeReport&&<div className="wiw-location-backdrop" role="dialog" aria-modal="true" aria-label="Arbeitszeit eintragen">
      <div className="wiw-location-modal">
        <div className="wiw-location-symbol"><IonIcon icon={stopwatchOutline}/></div>
        <h2>Wie lange hast du heute gearbeitet?</h2>
        <p>{day(timeReport.shift.starts_at)} · {timeReport.shift.position_name || 'Einsatz'} · {timeReport.shift.location_name || ''}</p>
        <p>Geplant: {time(timeReport.shift.starts_at)}–{time(timeReport.shift.ends_at)}. Bitte trage deine tatsächliche Arbeitszeit ein.</p>
        <div className="wiw-time-report-fields">
          <GermanTimeField label="Von" value={timeReport.clock_in} disabled={timeReportBusy} onChange={(value)=>setTimeReport({...timeReport,clock_in:value})}/>
          <GermanTimeField label="Bis" value={timeReport.clock_out} disabled={timeReportBusy} onChange={(value)=>setTimeReport({...timeReport,clock_out:value})}/>
        </div>
        {notice&&<div className="wiw-location-error">{notice}</div>}
        <button type="button" className="activate" disabled={timeReportBusy} onClick={requestTimeReportSubmit}>{timeReportBusy?'Wird gesendet …':'Zur Freigabe senden'}</button>
        <button type="button" className="cancel" disabled={timeReportBusy} onClick={postponeTimeReport}>Später</button>
      </div>
    </div>}

    <TimeReportLegalConfirmation open={timeReportLegalOpen} busy={timeReportBusy} onCancel={()=>setTimeReportLegalOpen(false)} onConfirm={()=>void submitTimeReport()}/>

    {clockIntent&&<div className="wiw-location-backdrop" role="dialog" aria-modal="true" aria-label="Standortberechtigung">
      <div className="wiw-location-modal">
        <div className="wiw-location-symbol"><IonIcon icon={locationOutline}/></div>
        <h2>Für die Zeiterfassung ist eine Berechtigung zur Standortbestimmung erforderlich</h2>
        <p>Aktiviere die Standortdienste, damit A+ weiß, wo du deine Arbeitszeit {clockIntent==='in'?'beginnst':'beendest'}.</p>
        {notice&&<div className="wiw-location-error">{notice}</div>}
        <button type="button" className="activate" disabled={clockBusy} onClick={()=>void clock(clockIntent, true)}>{clockBusy?'Standort wird bestimmt …':'Standortdienste aktivieren'}</button>
        <button type="button" className="cancel" disabled={clockBusy} onClick={()=>{setClockIntent('');setNotice('');}}>Abbrechen</button>
      </div>
    </div>}
  </>;
}

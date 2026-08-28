import React, { useMemo, useState } from 'react';
import { IonIcon } from '@ionic/react';
import { chevronBackOutline, timeOutline } from 'ionicons/icons';

const TZ='Europe/Berlin';
const fmtMonth=(date:Date)=>new Intl.DateTimeFormat('de-DE',{month:'long',timeZone:TZ}).format(date);
const fmtDate=(value:string)=>new Date(value).toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit',year:'numeric',timeZone:TZ});
const fmtTime=(value:string)=>new Date(value).toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit',timeZone:TZ});

function firstOfMonth(date:Date){return new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth(),1,12));}
function monthStart(offset:number,from=firstOfMonth(new Date())){return new Date(Date.UTC(from.getUTCFullYear(),from.getUTCMonth()+offset,1,12));}
function key(date:Date){return `${date.getUTCFullYear()}-${String(date.getUTCMonth()+1).padStart(2,'0')}`;}
function label(start:Date,end:Date){return `1. ${fmtMonth(start)} – 1. ${fmtMonth(end)} ${end.getUTCFullYear()}`;}
function monthDistance(newer:Date,older:Date){return (newer.getUTCFullYear()-older.getUTCFullYear())*12+(newer.getUTCMonth()-older.getUTCMonth());}

export default function Phase8MobileAttendance({data,showWorker=false}:{data:any;showWorker?:boolean}){
  const history=useMemo(()=>Array.isArray(data.history)?data.history:[],[data.history]);
  const periods=useMemo(()=>{
    const current=firstOfMonth(new Date());
    const valid=history.map((entry:any)=>entry?.clock_in?new Date(entry.clock_in):undefined).filter((entry:any)=>entry&&!Number.isNaN(entry.getTime())) as Date[];
    const earliest=valid.length?firstOfMonth(new Date(Math.min(...valid.map(item=>item.getTime())))):monthStart(-12,current);
    const count=Math.max(1,monthDistance(current,earliest)+1);
    return Array.from({length:count},(_,index)=>{
      const start=monthStart(-index,current),end=monthStart(1-index,current);
      return {key:key(start),start,end,label:label(start,end)};
    });
  },[history]);
  const [selected,setSelected]=useState<string>();
  const period=periods.find(item=>item.key===selected);
  const entries=useMemo(()=>{
    if(!period)return [];
    return history.filter((entry:any)=>{
      const value=new Date(entry.clock_in).getTime();
      return value>=period.start.getTime()&&value<period.end.getTime();
    }).sort((a:any,b:any)=>new Date(b.clock_in).getTime()-new Date(a.clock_in).getTime());
  },[history,period]);
  const minutes=entries.reduce((sum:number,entry:any)=>{
    if(!entry.clock_in||!entry.clock_out)return sum;
    return sum+Math.max(0,Math.round((new Date(entry.clock_out).getTime()-new Date(entry.clock_in).getTime())/60000)-Number(entry.break_minutes||0));
  },0);

  if(period){
    return <div className="wiw-pay-period-detail" data-testid="phase8-pay-period-detail">
      <button className="wiw-period-back" type="button" onClick={()=>setSelected(undefined)}><IonIcon icon={chevronBackOutline}/>Abrechnungszeiträume</button>
      <div className="wiw-period-title"><small>Abrechnungszeitraum</small><h1>{period.label}</h1><strong>{Math.floor(minutes/60)}:{String(minutes%60).padStart(2,'0')} Std.</strong></div>
      <div className="wiw-section-label">Arbeitszeiten</div>
      {entries.map((entry:any)=><div className="wiw-time-entry" key={entry.id}>
        <span className="wiw-row-icon"><IonIcon icon={timeOutline}/></span>
        <div><strong>{showWorker && entry.worker_name ? `${entry.worker_name} · ` : ''}{fmtDate(entry.clock_in)}</strong><span>{fmtTime(entry.clock_in)} – {entry.clock_out?fmtTime(entry.clock_out):'läuft'}</span><small>{entry.shift_title||'Arbeitszeit'}</small></div>
      </div>)}
      {!entries.length&&<div className="wiw-period-empty">Keine Arbeitszeiten in diesem Zeitraum.</div>}
    </div>;
  }

  return <div className="wiw-pay-periods" data-testid="phase8-pay-periods">
    <div className="wiw-mobile-screen-title">Abrechnungszeiträume</div>
    {periods.map(item=><button type="button" className="wiw-period-row" key={item.key} onClick={()=>setSelected(item.key)}>
      <strong>{item.label}</strong>
      <span className="wiw-period-circle" aria-hidden="true"/>
    </button>)}
  </div>;
}

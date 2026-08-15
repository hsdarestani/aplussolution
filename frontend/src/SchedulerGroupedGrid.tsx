import React, { useMemo } from 'react';
import { IonBadge } from '@ionic/react';
import type { CalendarMode } from './SchedulerCalendar';

const dateKey=(d:Date|string)=>{const x=typeof d==='string'?new Date(d):d;return `${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`};
const startDay=(d:Date)=>{const x=new Date(d);x.setHours(0,0,0,0);return x};
const addDays=(d:Date,n:number)=>{const x=new Date(d);x.setDate(x.getDate()+n);return x};
const weekStart=(d:Date)=>{const x=startDay(d);x.setDate(x.getDate()-((x.getDay()+6)%7));return x};
function daysFor(mode:CalendarMode,anchor:Date){if(mode==='day')return[startDay(anchor)];if(mode==='week'||mode==='twoWeeks'){const start=weekStart(anchor);return Array.from({length:mode==='week'?7:14},(_,i)=>addDays(start,i))}const first=new Date(anchor.getFullYear(),anchor.getMonth(),1);const start=weekStart(first);const last=new Date(anchor.getFullYear(),anchor.getMonth()+1,0);const finish=addDays(weekStart(last),7);const count=Math.min(42,Math.max(35,Math.round((finish.getTime()-start.getTime())/86400000)));return Array.from({length:count},(_,i)=>addDays(start,i))}
const time=(v:string)=>new Date(v).toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
type SchedulerGroup={id:string;name:string;rows:any[]};
const newGroup=(id:string,name:string):SchedulerGroup=>({id,name,rows:[]});

export default function SchedulerGroupedGrid({rows,mode,anchor,groupBy,onMove,onInspect,selected,onToggleSelect}:{rows:any[];mode:CalendarMode;anchor:Date;groupBy:'users'|'positions';onMove:(shift:any,targetDay:Date)=>Promise<void>|void;onInspect:(shift:any)=>void;selected:Set<string>;onToggleSelect:(id:string)=>void}){
  const days=useMemo(()=>daysFor(mode,anchor),[mode,anchor.getTime()]);
  const groups=useMemo(()=>{
    const map=new Map<string,SchedulerGroup>();
    if(groupBy==='positions'){
      for(const shift of rows){const id=String(shift.position);const group=map.get(id)||newGroup(id,shift.position_name||'Position');group.rows.push(shift);map.set(id,group)}
    }else{
      for(const shift of rows){
        for(const assignment of shift.assignments||[]){const id=String(assignment.worker);const group=map.get(id)||newGroup(id,assignment.worker_name||'Mitarbeiter');group.rows.push(shift);map.set(id,group)}
        if(Number(shift.open_count||0)>0){const group=map.get('__open__')||newGroup('__open__','Offene Schichten');group.rows.push(shift);map.set('__open__',group)}
      }
    }
    return [...map.values()].sort((a,b)=>a.id==='__open__'?1:b.id==='__open__'?-1:a.name.localeCompare(b.name,'de'));
  },[rows,groupBy]);

  function drop(event:React.DragEvent,day:Date){event.preventDefault();const id=event.dataTransfer.getData('text/shift-id');const shift=rows.find(x=>x.id===id);if(shift)void onMove(shift,day)}

  return <div className="scheduler-matrix-wrap"><div className="scheduler-matrix" style={{gridTemplateColumns:`190px repeat(${days.length}, minmax(145px,1fr))`}}>
    <div className="scheduler-matrix-corner">{groupBy==='users'?'Mitarbeiter':'Position'}</div>
    {days.map(day=><div key={dateKey(day)} className={`scheduler-matrix-dayhead ${dateKey(day)===dateKey(new Date())?'today':''}`}><small>{day.toLocaleDateString('de-DE',{weekday:'short'})}</small><b>{day.getDate()}</b></div>)}
    {groups.map(group=><React.Fragment key={group.id}><div className={`scheduler-matrix-group ${group.id==='__open__'?'open':''}`}><b>{group.name}</b><small>{group.rows.length} Schicht(en)</small></div>{days.map(day=>{const dayRows=group.rows.filter(x=>dateKey(x.starts_at)===dateKey(day));return <div className="scheduler-matrix-cell" key={`${group.id}-${dateKey(day)}`} onDragOver={e=>e.preventDefault()} onDrop={e=>drop(e,day)}>{dayRows.map(shift=><article draggable key={`${group.id}-${shift.id}`} className={`scheduler-mini-shift ${shift.status} ${selected.has(shift.id)?'selected':''}`} onDragStart={e=>{e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/shift-id',shift.id)}}><button aria-label="Auswählen" onClick={e=>{e.stopPropagation();onToggleSelect(shift.id)}}>{selected.has(shift.id)?'✓':'○'}</button><div onClick={()=>onInspect(shift)}><span>{time(shift.starts_at)}–{time(shift.ends_at)}</span><b>{groupBy==='users'?shift.position_name:shift.client_name}</b><small>{shift.location_name}</small></div>{Number(shift.open_count||0)>0&&<IonBadge color="warning">{shift.open_count} offen</IonBadge>}</article>)}{!dayRows.length&&<span className="scheduler-matrix-empty">·</span>}</div>})}</React.Fragment>)}
    {!groups.length&&<div className="scheduler-matrix-no-groups">Keine passenden Schichten für diese Ansicht.</div>}
  </div></div>
}

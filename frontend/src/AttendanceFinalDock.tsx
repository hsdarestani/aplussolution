import React, { useEffect, useMemo, useState } from 'react';
import { api, apiAll, me, User } from './api';
import './attendance-final.css';

type Tab = 'notices' | 'ip' | 'terminals';

const unpack = (value:any) => (Array.isArray(value) ? value : value?.results || []);
const fmt = (value?:string) => value ? new Date(value).toLocaleString('de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : '–';
const noticeLabel:Record<string,string> = {
  missed_clock_in:'Einstempeln fehlt', no_show:'Nicht erschienen', missed_clock_out:'Ausstempeln fehlt',
  late_clock_in:'Zu spät eingestempelt', early_clock_in:'Zu früh eingestempelt', wrong_location:'Standort/IP nicht freigegeben',
  early_clock_out:'Zu früh ausgestempelt', late_clock_out:'Zu spät ausgestempelt', not_scheduled:'Nicht eingeplant',
  break_missed:'Pause fehlt', break_short:'Pause zu kurz', attestation_missing:'Bestätigung fehlt', photo_missing:'Foto fehlt',
};

export default function AttendanceFinalDock(){
  const [user,setUser]=useState<User|null>(null);
  const [open,setOpen]=useState(false);
  const [tab,setTab]=useState<Tab>('notices');
  const [snapshot,setSnapshot]=useState<any>();
  const [policies,setPolicies]=useState<any[]>([]);
  const [locations,setLocations]=useState<any[]>([]);
  const [terminals,setTerminals]=useState<any[]>([]);
  const [policy,setPolicy]=useState<any>();
  const [terminal,setTerminal]=useState<any>();
  const [secret,setSecret]=useState<any>();
  const [timeEntry,setTimeEntry]=useState<any>();
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');

  const allowed = !!user && (user.role==='admin'||user.role==='manager');
  const currentNotices = snapshot?.notices || [];
  const sevenDays = snapshot?.notice_window_days || 7;
  const ipNetworks = useMemo(()=>Array.isArray(policy?.allowed_ip_networks)?policy.allowed_ip_networks.join('\n'):'',[policy]);

  async function load(){
    if(!localStorage.getItem('access'))return;
    try{
      const current=await me();setUser(current);
      if(!['admin','manager'].includes(current.role))return;
      const [exceptions,policyRows,terminalRows,locationRows]=await Promise.all([
        api('attendance/exceptions/'),api('attendance-policies/'),api('attendance-terminals/'),apiAll('locations/'),
      ]);
      setSnapshot(exceptions);setPolicies(unpack(policyRows));setTerminals(unpack(terminalRows));setLocations(locationRows);
      setPolicy((old:any)=>old||unpack(policyRows)[0]);
    }catch(e:any){setError(e?.message||'Attendance konnte nicht geladen werden.');}
  }

  useEffect(()=>{void load();const auth=()=>void load();window.addEventListener('storage',auth);window.addEventListener('auth-lost',auth);return()=>{window.removeEventListener('storage',auth);window.removeEventListener('auth-lost',auth)}},[]);
  useEffect(()=>{if(open&&allowed)void load()},[open]);

  async function run(task:()=>Promise<any>,success:string){
    setBusy(true);setError('');setNotice('');
    try{const result=await task();setNotice(success);await load();return result;}catch(e:any){setError(e?.message||'Aktion fehlgeschlagen.');return null;}finally{setBusy(false);}
  }

  async function saveIp(){
    if(!policy)return;
    const networks=String((document.getElementById('att-final-ip-list') as HTMLTextAreaElement)?.value||'').split(/[,\n]/).map(x=>x.trim()).filter(Boolean);
    const result=await run(()=>api(`attendance-policies/${policy.id}/`,{method:'PATCH',body:JSON.stringify({computer_ip_mode:policy.computer_ip_mode||'off',allowed_ip_networks:networks})}),'IP-Regel gespeichert.');
    if(result)setPolicy(result);
  }
  async function clearRecent(){await run(()=>api('attendance-notices/clear-recent/',{method:'POST',body:'{}'}),`${sevenDays}-Tage-Ansicht geleert.`)}
  async function remind(id:string){await run(()=>api(`attendance-notices/${id}/remind/`,{method:'POST',body:'{}'}),'Erinnerung gesendet.')}
  async function absence(id:string){await run(()=>api(`attendance-notices/${id}/report-absence/`,{method:'POST',body:JSON.stringify({note:'Aus der Attendance-Ansicht gemeldet.'})}),'Ausfall an Coverage übergeben.')}
  async function createTimeEntry(){
    if(!timeEntry?.notice||!timeEntry?.clock_in)return;
    const body:any={clock_in:new Date(timeEntry.clock_in).toISOString(),reason:timeEntry.reason||'Manuell aus Attendance Notice erstellt.'};
    if(timeEntry.clock_out)body.clock_out=new Date(timeEntry.clock_out).toISOString();
    const result=await run(()=>api(`attendance-notices/${timeEntry.notice}/create-time-entry/`,{method:'POST',body:JSON.stringify(body)}),'Zeiteintrag erstellt.');
    if(result)setTimeEntry(undefined);
  }
  async function createTerminal(){
    if(!terminal?.name){setError('Terminal-Name ist erforderlich.');return;}
    if((terminal.scope_mode||'location')==='location'&&!terminal.location){setError('Bitte einen Einsatzplan auswählen.');return;}
    const payload={name:terminal.name,scope_mode:terminal.scope_mode||'location',location:(terminal.scope_mode||'location')==='all'?null:terminal.location,photo_clock_in:!!terminal.photo_clock_in,photo_clock_out:!!terminal.photo_clock_out,active:true};
    const result=await run(()=>api('attendance-terminals/',{method:'POST',body:JSON.stringify(payload)}),'Terminal angelegt.');
    if(result?.terminal_token){setSecret(result);setTerminal(undefined);}
  }
  async function rotate(item:any){const result=await run(()=>api(`attendance-terminals/${item.id}/rotate-token/`,{method:'POST',body:'{}'}),'Terminal Secret erneuert.');if(result?.terminal_token)setSecret({...item,...result});}

  if(!allowed)return null;
  return <>
    <button className="att-final-launcher" data-testid="attendance-final-launcher" onClick={()=>setOpen(true)} aria-label="Attendance Plus"><span>✓</span><b>Attendance+</b>{currentNotices.length>0&&<i>{currentNotices.length}</i>}</button>
    {open&&<div className="att-final-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setOpen(false)}}>
      <section className="att-final-shell" role="dialog" aria-label="Attendance Plus" data-testid="attendance-final-panel">
        <header><div><small>A+ WORKFORCE · FINAL ATTENDANCE</small><h2>Time & Attendance vollständig steuern</h2><p>7-Tage-Notices, Computer-IP und Time Clock Terminals.</p></div><button onClick={()=>setOpen(false)}>✕</button></header>
        <nav><button className={tab==='notices'?'active':''} onClick={()=>setTab('notices')}>Notices · {sevenDays} Tage</button><button className={tab==='ip'?'active':''} onClick={()=>setTab('ip')}>IP-Regeln</button><button className={tab==='terminals'?'active':''} onClick={()=>setTab('terminals')}>Terminals</button></nav>
        {error&&<div className="att-final-alert error">{error}</div>}{notice&&<div className="att-final-alert success">{notice}</div>}

        {tab==='notices'&&<main className="att-final-page">
          <div className="att-final-title"><div><small>ROLLING WINDOW</small><h3>Attendance Notices der letzten {sevenDays} Tage</h3><p>Missed Clock-In bleibt während der Schicht offen und wird erst nach Schichtende zu No-Show.</p></div><button disabled={busy||!currentNotices.length} onClick={()=>void clearRecent()}>Ansicht leeren</button></div>
          <div className="att-final-stats"><article><span>Offen</span><b>{snapshot?.counts?.attendance_notices||0}</b></article><article><span>Kritisch</span><b>{snapshot?.counts?.critical_notices||0}</b></article><article><span>Korrekturen</span><b>{snapshot?.counts?.pending_corrections||0}</b></article><article><span>Offene Timer</span><b>{snapshot?.counts?.long_running_entries||0}</b></article></div>
          <div className="att-final-list">{currentNotices.map((row:any)=><article key={row.id} className={row.severity==='critical'?'critical':''}>
            <div><small>{row.severity?.toUpperCase()} · {fmt(row.detected_at)}</small><b>{row.worker_name}</b><strong>{noticeLabel[row.notice_type]||row.notice_type}</strong><p>{row.shift_title||'Arbeitszeit'}{row.location_name?` · ${row.location_name}`:''}{row.details?.restriction==='ip'&&row.details?.ip_address?` · IP ${row.details.ip_address}`:''}</p></div>
            <div className="att-final-actions"><button onClick={()=>void remind(row.id)}>Erinnern</button>{['missed_clock_in','no_show'].includes(row.notice_type)&&<button onClick={()=>void absence(row.id)}>Ausfall melden</button>}{['missed_clock_in','no_show'].includes(row.notice_type)&&<button className="primary" onClick={()=>setTimeEntry({notice:row.id,worker:row.worker_name,clock_in:'',clock_out:'',reason:''})}>Zeit erfassen</button>}</div>
          </article>)}{!currentNotices.length&&<p className="att-final-empty">Keine offenen Notices in diesem Zeitraum.</p>}</div>
        </main>}

        {tab==='ip'&&<main className="att-final-page narrow">
          <div className="att-final-title"><div><small>PERSONAL COMPUTER</small><h3>Clock-In/Out nach IP begrenzen</h3><p>IP-Regeln gelten für Web/Computer. Mobile nutzt Standortregeln, Terminals sind davon ausgenommen.</p></div></div>
          <section className="att-final-card">
            <label>Attendance Policy<select value={policy?.id||''} onChange={e=>setPolicy(policies.find(x=>x.id===e.target.value))}><option value="">Policy auswählen</option>{policies.map(x=><option key={x.id} value={x.id}>{x.name}{x.location_name?` · ${x.location_name}`:' · Global'}</option>)}</select></label>
            {policy&&<><label>IP-Prüfung<select value={policy.computer_ip_mode||'off'} onChange={e=>setPolicy({...policy,computer_ip_mode:e.target.value})}><option value="off">Aus</option><option value="warn">Nur Hinweis</option><option value="block">Blockieren</option></select></label><label>Freigegebene IPs / CIDR<textarea id="att-final-ip-list" defaultValue={ipNetworks} placeholder={'203.0.113.42\n198.51.100.0/24'}/><small>Eine IP oder ein CIDR-Netz pro Zeile. IPv4 und IPv6 werden unterstützt.</small></label><button className="primary" disabled={busy} onClick={()=>void saveIp()}>IP-Regel speichern</button></>}
          </section>
          <div className="att-final-note"><b>No-Show Semantik</b><span>No-Show entsteht jetzt nach Ende der Schicht. Die alte Minuten-Einstellung wird für diese Statusumwandlung nicht mehr verwendet.</span></div>
        </main>}

        {tab==='terminals'&&<main className="att-final-page">
          <div className="att-final-title"><div><small>TIME CLOCK</small><h3>Terminal-Geltungsbereich</h3><p>Ein Gerät kann an einen Einsatzplan gebunden oder für alle Einsatzpläne freigegeben werden.</p></div><button className="primary" onClick={()=>setTerminal({scope_mode:'location',location:'',name:'',photo_clock_in:false,photo_clock_out:false})}>Terminal anlegen</button></div>
          <div className="att-final-list terminals">{terminals.map((row:any)=><article key={row.id}><div><small>{row.active?'AKTIV':'INAKTIV'}</small><b>{row.name}</b><strong>{row.scope_mode==='all'?'Alle Einsatzpläne':row.location_name}</strong><p>{row.photo_clock_in||row.photo_clock_out?'Foto-Regel aktiv':'Ohne Terminal-Foto'} · zuletzt {fmt(row.last_seen_at)}</p></div><div className="att-final-actions"><button onClick={()=>void rotate(row)}>Secret erneuern</button></div></article>)}{!terminals.length&&<p className="att-final-empty">Noch kein Terminal eingerichtet.</p>}</div>
        </main>}
      </section>
    </div>}

    {terminal&&<div className="att-final-modal-bg"><section className="att-final-modal"><header><div><small>TIME CLOCK TERMINAL</small><h3>Terminal anlegen</h3></div><button onClick={()=>setTerminal(undefined)}>✕</button></header><label>Name<input value={terminal.name||''} onChange={e=>setTerminal({...terminal,name:e.target.value})}/></label><label>Geltungsbereich<select value={terminal.scope_mode||'location'} onChange={e=>setTerminal({...terminal,scope_mode:e.target.value,location:e.target.value==='all'?'':terminal.location})}><option value="location">Bestimmter Einsatzplan</option><option value="all">Alle Einsatzpläne</option></select></label>{terminal.scope_mode!=='all'&&<label>Einsatzplan<select value={terminal.location||''} onChange={e=>setTerminal({...terminal,location:e.target.value})}><option value="">Auswählen</option>{locations.map(x=><option value={x.id} key={x.id}>{x.name}</option>)}</select></label>}<label className="att-final-check"><input type="checkbox" checked={!!terminal.photo_clock_in} onChange={e=>setTerminal({...terminal,photo_clock_in:e.target.checked})}/> Foto beim Einstempeln</label><label className="att-final-check"><input type="checkbox" checked={!!terminal.photo_clock_out} onChange={e=>setTerminal({...terminal,photo_clock_out:e.target.checked})}/> Foto beim Ausstempeln</label><footer><button onClick={()=>setTerminal(undefined)}>Abbrechen</button><button className="primary" disabled={busy} onClick={()=>void createTerminal()}>Anlegen</button></footer></section></div>}

    {secret&&<div className="att-final-modal-bg"><section className="att-final-modal secret"><header><div><small>NUR EINMAL SICHTBAR</small><h3>Terminal Secret</h3></div><button onClick={()=>setSecret(undefined)}>✕</button></header><p>Terminal URL</p><code>{`${window.location.origin}/terminal/${secret.public_id}`}</code><p>Secret</p><code>{secret.terminal_token}</code><footer><button className="primary" onClick={()=>setSecret(undefined)}>Verstanden</button></footer></section></div>}

    {timeEntry&&<div className="att-final-modal-bg"><section className="att-final-modal"><header><div><small>MANUELLER ZEITEINTRAG</small><h3>{timeEntry.worker}</h3></div><button onClick={()=>setTimeEntry(undefined)}>✕</button></header><label>Beginn<input type="datetime-local" value={timeEntry.clock_in} onChange={e=>setTimeEntry({...timeEntry,clock_in:e.target.value})}/></label><label>Ende (optional)<input type="datetime-local" value={timeEntry.clock_out} onChange={e=>setTimeEntry({...timeEntry,clock_out:e.target.value})}/></label><label>Grund<textarea value={timeEntry.reason} onChange={e=>setTimeEntry({...timeEntry,reason:e.target.value})}/></label><footer><button onClick={()=>setTimeEntry(undefined)}>Abbrechen</button><button className="primary" disabled={busy||!timeEntry.clock_in} onClick={()=>void createTimeEntry()}>Zeiteintrag erstellen</button></footer></section></div>}
  </>;
}

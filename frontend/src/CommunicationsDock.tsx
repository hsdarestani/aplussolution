import React, { useEffect, useMemo, useRef, useState } from 'react';
import { api, me, User } from './api';
import { initNativePush } from './push';
import './communications-v6.css';

type Tab = 'chat' | 'notifications' | 'preferences';
type Snapshot = { unread_notifications:number; unread_chat:number; devices:number; settings:any };
type ChatUser = { id:string; name:string; email:string; role:string; avatar?:string|null };
type Channel = {
  id:string; title:string; channel_type:'workplace'|'group'|'direct'; pinned:boolean; unread_count:number;
  can_post:boolean; can_manage:boolean; can_leave:boolean; muted:boolean; participants_detail:ChatUser[];
  messages?:Message[];
};
type Message = { id:string; sender?:string; sender_detail?:ChatUser; body:string; attachment?:string|null; created_at:string; mine:boolean; deleted_at?:string|null; read_count:number };
type Notice = { id:string; title:string; body:string; category:string; priority:string; action_url:string; is_read:boolean; created_at:string; data?:any };
type Preference = { id:string; category:string; category_label:string; in_app_enabled:boolean; push_enabled:boolean; email_enabled:boolean; sms_enabled:boolean; reminder_minutes:number; dnd_start?:string|null; dnd_end?:string|null };

const unpack = <T,>(data:any):T[] => (data?.results || data || []) as T[];
const dt = (value:string) => new Date(value).toLocaleString('de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});

export default function CommunicationsDock() {
  const [user,setUser]=useState<User|null>(null);
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
  const [open,setOpen]=useState(false);
  const [tab,setTab]=useState<Tab>('chat');
  const [channels,setChannels]=useState<Channel[]>([]);
  const [selected,setSelected]=useState<string>('');
  const [notices,setNotices]=useState<Notice[]>([]);
  const [preferences,setPreferences]=useState<Preference[]>([]);
  const [candidates,setCandidates]=useState<ChatUser[]>([]);
  const [settings,setSettings]=useState<any>(null);
  const [body,setBody]=useState('');
  const [image,setImage]=useState<File|null>(null);
  const [newTitle,setNewTitle]=useState('');
  const [newMembers,setNewMembers]=useState<string[]>([]);
  const [creating,setCreating]=useState(false);
  const [showSettings,setShowSettings]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const fileRef=useRef<HTMLInputElement>(null);

  const active=useMemo(()=>channels.find(item=>item.id===selected),[channels,selected]);
  const totalUnread=(snapshot?.unread_chat||0)+(snapshot?.unread_notifications||0);

  async function bootstrap() {
    if (!localStorage.getItem('access')) { setUser(null); return; }
    try {
      const current=await me(); setUser(current); void initNativePush();
      await refreshSnapshot();
    } catch { setUser(null); }
  }
  async function refreshSnapshot(){ try{setSnapshot(await api('communications/snapshot/'));}catch{/* authenticated shell may still be loading */} }
  async function loadChat(selectId?:string){
    const rows=unpack<Channel>(await api('conversations/')); setChannels(rows);
    const target=selectId || selected || rows[0]?.id || ''; setSelected(target);
    if(target) await api(`conversations/${target}/mark_read/`,{method:'POST',body:'{}'}).catch(()=>undefined);
    await refreshSnapshot();
  }
  async function loadNotices(){ setNotices(unpack(await api('notifications/'))); await refreshSnapshot(); }
  async function loadPreferences(){ setPreferences(unpack(await api('notification-preferences/'))); }
  async function loadSettings(){ setSettings(await api('communications/settings/')); }
  async function loadCandidates(){ setCandidates(unpack(await api('communications/candidates/'))); }

  useEffect(()=>{ void bootstrap(); const auth=()=>void bootstrap(); window.addEventListener('auth-lost',auth); window.addEventListener('storage',auth); return()=>{window.removeEventListener('auth-lost',auth);window.removeEventListener('storage',auth);};},[]);
  useEffect(()=>{ if(!user)return; const timer=window.setInterval(()=>void refreshSnapshot(),30000); return()=>window.clearInterval(timer);},[user]);
  useEffect(()=>{
    const refresh=()=>{if(user){void refreshSnapshot(); if(open&&tab==='notifications')void loadNotices(); if(open&&tab==='chat')void loadChat();}};
    const openFromPush=(event:Event)=>{const detail=(event as CustomEvent).detail||{}; setOpen(true); if(detail.category==='workchat'||detail.conversation_id){setTab('chat');void loadChat(detail.conversation_id);}else{setTab('notifications');void loadNotices();}};
    window.addEventListener('aplus-communications-refresh',refresh); window.addEventListener('aplus-communications-open',openFromPush);
    return()=>{window.removeEventListener('aplus-communications-refresh',refresh);window.removeEventListener('aplus-communications-open',openFromPush);};
  },[user,open,tab]);

  useEffect(()=>{ if(!open||!user)return; setError(''); if(tab==='chat')void loadChat(); if(tab==='notifications')void loadNotices(); if(tab==='preferences')void Promise.all([loadPreferences(),loadSettings()]);},[open,tab,user]);

  async function chooseChannel(id:string){setSelected(id);await api(`conversations/${id}/mark_read/`,{method:'POST',body:'{}'});await loadChat(id);}
  async function send(){
    if(!active||(!body.trim()&&!image))return; setBusy(true);setError('');
    try{
      let payload:BodyInit;
      if(image){const form=new FormData();form.append('body',body);form.append('image',image);payload=form;}else payload=JSON.stringify({body});
      await api(`conversations/${active.id}/post_message/`,{method:'POST',body:payload});setBody('');setImage(null);if(fileRef.current)fileRef.current.value='';await loadChat(active.id);
    }catch(e:any){setError(e.message);}finally{setBusy(false);}
  }
  async function createChannel(){
    if(!newMembers.length)return;setBusy(true);setError('');try{const row:any=await api('conversations/',{method:'POST',body:JSON.stringify({title:newTitle,participants:newMembers})});setCreating(false);setNewTitle('');setNewMembers([]);await loadChat(row.id);}catch(e:any){setError(e.message);}finally{setBusy(false);}
  }
  async function deleteMessage(id:string){if(!confirm('Eigene Nachricht löschen?'))return;await api(`workchat/messages/${id}/delete/`,{method:'DELETE'});await loadChat(active?.id);}
  async function leave(){if(!active||!confirm('Diesen Kanal verlassen?'))return;await api(`conversations/${active.id}/leave/`,{method:'POST',body:'{}'});setSelected('');await loadChat();}
  async function toggleMute(){if(!active)return;await api(`conversations/${active.id}/mute/`,{method:'POST',body:JSON.stringify({muted:!active.muted})});await loadChat(active.id);}
  async function markNotice(n:Notice){if(!n.is_read)await api(`notifications/${n.id}/mark_read/`,{method:'POST',body:'{}'});if(n.data?.conversation_id){setTab('chat');await loadChat(n.data.conversation_id);return;}if(n.action_url?.includes('messages')){setTab('chat');await loadChat();return;}await loadNotices();}
  async function deleteNotice(id:string){await api(`notifications/${id}/`,{method:'DELETE'});await loadNotices();}
  async function markAll(){await api('notifications/mark_all_read/',{method:'POST',body:'{}'});await loadNotices();}
  async function savePref(pref:Preference,patch:Partial<Preference>){
    const next={...pref,...patch};setPreferences(items=>items.map(x=>x.id===pref.id?next:x));
    try{const saved:any=await api(`notification-preferences/${pref.id}/configure/`,{method:'PATCH',body:JSON.stringify(patch)});setPreferences(items=>items.map(x=>x.id===pref.id?saved:x));}catch(e:any){setError(e.message);await loadPreferences();}
  }
  async function saveSettings(patch:any){if(!settings?.can_manage)return;setBusy(true);setError('');try{const saved=await api('communications/settings/',{method:'PATCH',body:JSON.stringify(patch)});setSettings(saved);await refreshSnapshot();}catch(e:any){if(e.message.includes('ausdrücklich bestätigen')&&confirm('WorkChat deaktivieren und gesamten WorkChat-Verlauf löschen?')){const saved=await api('communications/settings/',{method:'PATCH',body:JSON.stringify({...patch,confirm_delete_history:true})});setSettings(saved);}else setError(e.message);}finally{setBusy(false);}}

  if(!user)return null;
  return <>
    <div className="comms-dock-launchers" data-testid="communications-dock">
      <button onClick={()=>{setTab('chat');setOpen(true)}} aria-label="WorkChat öffnen"><span>💬</span>{(snapshot?.unread_chat||0)>0&&<b>{snapshot!.unread_chat}</b>}</button>
      <button onClick={()=>{setTab('notifications');setOpen(true)}} aria-label="Benachrichtigungen öffnen"><span>🔔</span>{(snapshot?.unread_notifications||0)>0&&<b>{snapshot!.unread_notifications}</b>}</button>
      {totalUnread>0&&<i>{totalUnread}</i>}
    </div>
    {open&&<div className="comms-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setOpen(false)}}>
      <section className="comms-shell" role="dialog" aria-label="Kommunikation">
        <header><div><small>A+ WORKFORCE</small><h2>WorkChat & Benachrichtigungen</h2></div><button onClick={()=>setOpen(false)}>✕</button></header>
        <nav>
          <button className={tab==='chat'?'active':''} onClick={()=>setTab('chat')}>WorkChat {(snapshot?.unread_chat||0)>0&&<b>{snapshot?.unread_chat}</b>}</button>
          <button className={tab==='notifications'?'active':''} onClick={()=>setTab('notifications')}>Benachrichtigungen {(snapshot?.unread_notifications||0)>0&&<b>{snapshot!.unread_notifications}</b>}</button>
          <button className={tab==='preferences'?'active':''} onClick={()=>setTab('preferences')}>Einstellungen</button>
        </nav>
        {error&&<div className="comms-error">{error}</div>}

        {tab==='chat'&&<div className="comms-chat">
          <aside>
            <div className="comms-aside-head"><b>Kanäle</b><button onClick={async()=>{setCreating(true);await loadCandidates()}}>＋</button></div>
            {channels.map(ch=><button key={ch.id} className={selected===ch.id?'active':''} onClick={()=>void chooseChannel(ch.id)}><span>{ch.channel_type==='workplace'?'🏢':ch.channel_type==='direct'?'👤':'👥'}</span><div><b>{ch.title}</b><small>{ch.participants_detail.map(p=>p.name).slice(0,3).join(', ')}</small></div>{ch.unread_count>0&&<i>{ch.unread_count}</i>}</button>)}
            {!channels.length&&<p className="comms-empty">Noch keine Kanäle.</p>}
          </aside>
          <main>
            {active?<>
              <div className="comms-chat-head"><div><h3>{active.title}</h3><small>{active.participants_detail.length} Mitglieder · {active.channel_type==='workplace'?'Betriebskanal':active.channel_type==='direct'?'Direktnachricht':'Gruppe'}</small></div><div><button onClick={()=>void toggleMute()}>{active.muted?'🔕 Stumm':'🔔 Aktiv'}</button>{active.can_leave&&<button onClick={()=>void leave()}>Verlassen</button>}</div></div>
              <div className="comms-messages">{active.messages?.map(msg=><article className={msg.mine?'mine':''} key={msg.id}><div><b>{msg.sender_detail?.name||'System'}</b><small>{dt(msg.created_at)}</small></div><p>{msg.body}</p>{msg.attachment&&<a href={msg.attachment} target="_blank" rel="noreferrer"><img src={msg.attachment}/></a>}<footer>{msg.mine&&<span>Gelesen: {msg.read_count}</span>}{msg.mine&&!msg.deleted_at&&<button onClick={()=>void deleteMessage(msg.id)}>Löschen</button>}</footer></article>)}</div>
              <div className="comms-compose">{image&&<div className="comms-file">📎 {image.name}<button onClick={()=>setImage(null)}>✕</button></div>}<textarea disabled={!active.can_post} value={body} onChange={e=>setBody(e.target.value)} placeholder={active.can_post?'Nachricht schreiben …':'Dieser Kanal ist nur für Ankündigungen.'}/><input ref={fileRef} type="file" accept="image/png,image/jpeg,image/gif,image/webp" onChange={e=>setImage(e.target.files?.[0]||null)} hidden/><button disabled={!active.can_post} onClick={()=>fileRef.current?.click()}>📎</button><button className="primary" disabled={busy||!active.can_post} onClick={()=>void send()}>Senden</button></div>
            </>:<div className="comms-empty large">Kanal auswählen.</div>}
          </main>
        </div>}

        {tab==='notifications'&&<div className="comms-notifications"><div className="comms-section-head"><div><h3>Notification Center</h3><p>Neueste Meldungen zuerst. Aktionen bleiben direkt erreichbar.</p></div><button onClick={()=>void markAll()}>Alle gelesen</button></div>{notices.map(n=><article className={n.is_read?'read':''} key={n.id}><button className="comms-notice-body" onClick={()=>void markNotice(n)}><span className={`priority ${n.priority}`}></span><div><b>{n.title}</b><p>{n.body}</p><small>{dt(n.created_at)} · {n.category.replaceAll('_',' ')}</small></div></button><button onClick={()=>void deleteNotice(n.id)}>✕</button></article>)}{!notices.length&&<p className="comms-empty large">Keine Benachrichtigungen.</p>}</div>}

        {tab==='preferences'&&<div className="comms-preferences">
          <div className="comms-section-head"><div><h3>Alert Preferences</h3><p>In-App, Push, E-Mail und optional SMS pro Kategorie steuern.</p></div><button onClick={()=>setShowSettings(v=>!v)}>WorkChat Regeln</button></div>
          {showSettings&&settings&&<div className="comms-settings-card"><div><b>WorkChat global</b><label><input type="checkbox" checked={settings.workchat_enabled} disabled={!settings.can_manage||busy} onChange={e=>void saveSettings({workchat_enabled:e.target.checked})}/> Aktiv</label></div><div><b>Betriebskanal</b><label><input type="checkbox" checked={settings.employees_can_post_workplace} disabled={!settings.can_manage} onChange={e=>void saveSettings({employees_can_post_workplace:e.target.checked})}/> Mitarbeiter dürfen posten</label></div><div><b>Eigene Kanäle</b><label><input type="checkbox" checked={settings.users_can_create_channels} disabled={!settings.can_manage} onChange={e=>void saveSettings({users_can_create_channels:e.target.checked})}/> Benutzer dürfen Gruppen erstellen</label></div><div><b>Bilder</b><label><input type="checkbox" checked={settings.images_enabled} disabled={!settings.can_manage} onChange={e=>void saveSettings({images_enabled:e.target.checked})}/> Bildversand erlauben</label></div><div><b>SMS Fallback</b><label><input type="checkbox" checked={settings.sms_fallback_enabled} disabled={!settings.can_manage} onChange={e=>void saveSettings({sms_fallback_enabled:e.target.checked})}/> SMS aktivieren</label></div></div>}
          <div className="comms-pref-grid">{preferences.map(pref=><article key={pref.id}><div><b>{pref.category_label}</b>{pref.category==='shift_reminder'&&<small>Erinnerung {pref.reminder_minutes} Min. vorher</small>}</div><label><input type="checkbox" checked={pref.in_app_enabled} onChange={e=>void savePref(pref,{in_app_enabled:e.target.checked})}/> In-App</label><label><input type="checkbox" checked={pref.push_enabled} onChange={e=>void savePref(pref,{push_enabled:e.target.checked})}/> Push</label><label><input type="checkbox" checked={pref.email_enabled} onChange={e=>void savePref(pref,{email_enabled:e.target.checked})}/> E-Mail</label><label><input type="checkbox" checked={pref.sms_enabled} onChange={e=>void savePref(pref,{sms_enabled:e.target.checked})}/> SMS</label>{pref.category==='shift_reminder'&&<select value={pref.reminder_minutes} onChange={e=>void savePref(pref,{reminder_minutes:Number(e.target.value)})}><option value={15}>15 Min.</option><option value={30}>30 Min.</option><option value={60}>1 Std.</option><option value={120}>2 Std.</option><option value={720}>12 Std.</option><option value={1440}>24 Std.</option></select>}</article>)}</div>
        </div>}
      </section>
    </div>}
    {creating&&<div className="comms-modal-bg"><section className="comms-modal"><header><h3>Neuer WorkChat-Kanal</h3><button onClick={()=>setCreating(false)}>✕</button></header><input value={newTitle} onChange={e=>setNewTitle(e.target.value)} placeholder="Gruppenname (optional)"/><div className="comms-candidates">{candidates.map(person=><label key={person.id}><input type="checkbox" checked={newMembers.includes(person.id)} onChange={e=>setNewMembers(list=>e.target.checked?[...list,person.id]:list.filter(id=>id!==person.id))}/><span><b>{person.name}</b><small>{person.role} · {person.email}</small></span></label>)}</div><footer><button onClick={()=>setCreating(false)}>Abbrechen</button><button className="primary" disabled={!newMembers.length||busy} onClick={()=>void createChannel()}>Kanal erstellen</button></footer></section></div>}
  </>;
}

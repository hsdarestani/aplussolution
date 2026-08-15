import React, { useMemo, useRef, useState } from 'react';
import { IonButton, IonIcon, IonInput, IonSpinner } from '@ionic/react';
import { cameraOutline, checkmarkCircleOutline, pauseCircleOutline, playCircleOutline, timeOutline } from 'ionicons/icons';
import './time-clock-terminal.css';

const API = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace(/\/$/, '');

function terminalIdFromPath() {
  const match = window.location.pathname.match(/^\/terminal\/([^/]+)\/?$/);
  return match?.[1] || '';
}

export default function TimeClockTerminal() {
  const publicId = terminalIdFromPath();
  const storageKey = `aplus:terminal:${publicId}:secret`;
  const [secret, setSecret] = useState(() => localStorage.getItem(storageKey) || '');
  const [identity, setIdentity] = useState('');
  const [photo, setPhoto] = useState<File>();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>();
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const ready = useMemo(() => !!publicId && !!secret.trim() && !!identity.trim(), [publicId, secret, identity]);

  function saveSecret() {
    if (!secret.trim()) return;
    localStorage.setItem(storageKey, secret.trim());
    setResult({ message: 'Terminal Secret wurde auf diesem Gerät gespeichert.' });
  }

  async function send(action: 'clock_in'|'clock_out'|'break_start'|'break_end') {
    if (!ready) return;
    setBusy(true); setError(''); setResult(undefined);
    try {
      const form = new FormData();
      form.append('identity', identity.trim());
      form.append('action', action);
      form.append('terminal_token', secret.trim());
      if (photo && (action === 'clock_in' || action === 'clock_out')) form.append('photo', photo);
      const response = await fetch(`${API}/attendance/terminal/${publicId}/clock/`, { method: 'POST', body: form });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || 'Terminal-Aktion fehlgeschlagen.');
      setResult(body);
      setIdentity(''); setPhoto(undefined);
      if (fileRef.current) fileRef.current.value = '';
    } catch (reason: any) {
      setError(reason.message || 'Terminal-Aktion fehlgeschlagen.');
    } finally { setBusy(false); }
  }

  if (!publicId) return <div className="terminal-shell"><div className="terminal-card"><h1>Ungültige Terminal-URL</h1></div></div>;

  return <div className="terminal-shell">
    <main className="terminal-card" data-testid="time-clock-terminal">
      <div className="terminal-brand"><span>A+</span><div><small>WORKFORCE</small><b>Time Clock Terminal</b></div></div>
      {!localStorage.getItem(storageKey) && <section className="terminal-setup"><small>GERÄT EINRICHTEN</small><h1>Terminal Secret</h1><p>Das einmalige Secret aus der Administration auf diesem Gerät hinterlegen.</p><IonInput fill="outline" type="password" label="Terminal Secret" labelPlacement="floating" value={secret} onIonInput={(e)=>setSecret(String(e.detail.value||''))}/><IonButton expand="block" onClick={saveSecret}>Auf diesem Gerät speichern</IonButton></section>}
      {localStorage.getItem(storageKey) && <>
        <section className="terminal-clock"><IonIcon icon={timeOutline}/><strong>{new Date().toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'})}</strong><span>{new Date().toLocaleDateString('de-DE',{weekday:'long',day:'2-digit',month:'long'})}</span></section>
        <IonInput className="terminal-identity" fill="outline" label="Personalnummer oder E-Mail" labelPlacement="floating" value={identity} onIonInput={(e)=>setIdentity(String(e.detail.value||''))}/>
        <label className="terminal-photo"><input ref={fileRef} type="file" accept="image/*" capture="user" onChange={(e)=>setPhoto(e.target.files?.[0])}/><IonIcon icon={cameraOutline}/><span>{photo ? photo.name : 'Foto aufnehmen (falls erforderlich)'}</span></label>
        <div className="terminal-actions"><IonButton disabled={!ready||busy} onClick={()=>void send('clock_in')}><IonIcon slot="start" icon={playCircleOutline}/>Einstempeln</IonButton><IonButton color="danger" disabled={!ready||busy} onClick={()=>void send('clock_out')}><IonIcon slot="start" icon={checkmarkCircleOutline}/>Ausstempeln</IonButton><IonButton fill="outline" disabled={!ready||busy} onClick={()=>void send('break_start')}><IonIcon slot="start" icon={pauseCircleOutline}/>Pause starten</IonButton><IonButton fill="outline" disabled={!ready||busy} onClick={()=>void send('break_end')}><IonIcon slot="start" icon={playCircleOutline}/>Pause beenden</IonButton></div>
        {busy && <div className="terminal-status"><IonSpinner/><span>Wird gespeichert …</span></div>}
        {result && !busy && <div className="terminal-result success"><IonIcon icon={checkmarkCircleOutline}/><div><b>{result.worker_name || 'Terminal bereit'}</b><span>{result.action === 'clock_in' ? 'Erfolgreich eingestempelt.' : result.action === 'clock_out' ? 'Erfolgreich ausgestempelt.' : result.action === 'break_start' ? 'Pause gestartet.' : result.action === 'break_end' ? 'Pause beendet.' : result.message}</span></div></div>}
        {error && <div className="terminal-result error"><div><b>Aktion nicht möglich</b><span>{error}</span></div></div>}
        <button className="terminal-reset" onClick={()=>{localStorage.removeItem(storageKey);setSecret('');setResult(undefined);}}>Terminal Secret ändern</button>
      </>}
    </main>
  </div>;
}

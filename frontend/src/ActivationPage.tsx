import React, { useEffect, useState } from 'react';
import { IonButton, IonIcon, IonInput, IonSpinner } from '@ionic/react';
import { checkmarkCircleOutline, keyOutline, shieldCheckmarkOutline } from 'ionicons/icons';
import { api } from './api';
import './employee-portal.css';

export default function ActivationPage() {
  const token = new URLSearchParams(window.location.search).get('token') || '';
  const [info, setInfo] = useState<any>();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api('auth/activation/validate/', { method: 'POST', body: JSON.stringify({ token }) })
      .then(setInfo)
      .catch((reason) => setError(reason.message))
      .finally(() => setBusy(false));
  }, [token]);

  async function activate() {
    setBusy(true); setError('');
    try {
      const result:any = await api('auth/activation/complete/', {
        method: 'POST',
        body: JSON.stringify({ token, password, password_confirm: confirm }),
      });
      localStorage.setItem('access', result.access);
      localStorage.setItem('refresh', result.refresh);
      window.location.href = '/';
    } catch (reason:any) {
      setError(reason.message);
    } finally { setBusy(false); }
  }

  return <main className="activation-page">
    <section className="activation-card">
      <div className="activation-brand"><strong>A+</strong><span>Solution</span></div>
      {busy && !info ? <div className="activation-state"><IonSpinner/><p>Aktivierungslink wird geprüft …</p></div> : error && !info ? <div className="activation-state error"><h1>Link nicht verfügbar</h1><p>{error}</p></div> : <>
        <div className="activation-icon"><IonIcon icon={shieldCheckmarkOutline}/></div>
        <small>MITARBEITERPORTAL</small>
        <h1>Willkommen{info?.name ? `, ${String(info.name).split(' ')[0]}` : ''}.</h1>
        <p>Lege dein Passwort fest. Danach kannst du freie Schichten auswählen, deine Einsätze und Arbeitszeiten verwalten und Verträge digital bearbeiten.</p>
        <div className="activation-email">{info?.email}</div>
        <IonInput fill="outline" type="password" label="Neues Passwort" labelPlacement="floating" value={password} onIonInput={e=>setPassword(String(e.detail.value||''))}/>
        <IonInput fill="outline" type="password" label="Passwort wiederholen" labelPlacement="floating" value={confirm} onIonInput={e=>setConfirm(String(e.detail.value||''))}/>
        {error && <div className="activation-error">{error}</div>}
        <IonButton expand="block" disabled={busy || password.length < 10 || password !== confirm} onClick={activate}><IonIcon slot="start" icon={keyOutline}/>{busy ? 'Wird aktiviert …' : 'Portal aktivieren'}</IonButton>
        <div className="activation-benefits"><span><IonIcon icon={checkmarkCircleOutline}/> Eigene Schichten</span><span><IonIcon icon={checkmarkCircleOutline}/> Arbeitszeiten</span><span><IonIcon icon={checkmarkCircleOutline}/> Verträge & Dokumente</span></div>
      </>}
    </section>
  </main>;
}

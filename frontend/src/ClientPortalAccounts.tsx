import React, { useEffect, useState } from 'react';
import { IonButton, IonContent, IonModal, IonSpinner } from '@ionic/react';
import { api } from './api';
import './client-portal-accounts.css';

type Customer = { id: string; name: string };
type Place = { id: string; name: string; client?: string; active?: boolean };
type Department = { id: string; name: string; active?: boolean };
type Account = {
  id?: string;
  email: string;
  first_name: string;
  last_name: string;
  read_only: boolean;
  location_scope_id: string;
  position_ids: string[];
  is_active: boolean;
};
const blank = (): Account => ({
  email: '', first_name: '', last_name: '', read_only: true,
  location_scope_id: '', position_ids: [], is_active: true,
});

export default function ClientPortalAccounts({
  client, locations, positions, onClose,
}: {
  client: Customer | null;
  locations: Place[];
  positions: Department[];
  onClose: () => void;
}) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [form, setForm] = useState<Account>(blank());
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [credentials, setCredentials] = useState<{email: string; temporary_password: string} | null>(null);
  const allowedLocations = locations.filter((loc) => String(loc.client || '') === String(client?.id) && loc.active !== false);
  const allowedPositions = positions.filter((pos) => pos.active !== false);

  async function refresh(id: string) {
    const data: any = await api(`clients/${id}/portal-users/`);
    setAccounts(data.accounts || []);
  }

  useEffect(() => {
    setEditing(false);
    setForm(blank());
    setCredentials(null);
    setError('');
    setNotice('');
    setAccounts([]);
    if (client?.id) {
      void refresh(client.id).catch((err) => setError(err.message));
    }
  }, [client?.id]);

  function newAccount() {
    setEditing(true);
    setError('');
    setCredentials(null);
    setForm({ ...blank(), location_scope_id: allowedLocations.length === 1 ? allowedLocations[0].id : '' });
  }

  function choose(account: Account) {
    setEditing(true);
    setError('');
    setCredentials(null);
    setForm({ ...account, position_ids: [...(account.position_ids || [])] });
  }

  function togglePosition(id: string, enabled: boolean) {
    setForm((current) => ({
      ...current,
      position_ids: enabled
        ? [...current.position_ids, id]
        : current.position_ids.filter((item) => item !== id),
    }));
  }

  async function save() {
    if (!client?.id || busy) return;
    setError('');
    if (!form.email.trim() || !form.first_name.trim() || !form.last_name.trim()) {
      setError('Bitte Vorname, Nachname und E Mail Adresse angeben.');
      return;
    }
    if (form.read_only && !form.location_scope_id) {
      setError('Bitte einen Standort auswählen.');
      return;
    }
    setBusy(true);
    try {
      const method = form.id ? 'PATCH' : 'POST';
      const endpoint = `clients/${client.id}/portal-users/${form.id ? `${form.id}/` : ''}`;
      const result: any = await api(endpoint, {
        method, body: JSON.stringify(form),
      });
      if (result.temporary_password) {
        setCredentials({ email: form.email, temporary_password: result.temporary_password });
      }
      await refresh(client.id);
      setNotice(form.id ? 'Zugangsrechte wurden aktualisiert.' : 'Neuer Zugang wurde erstellt.');
      setEditing(false);
    } catch (err: any) {
      setError(err?.message || 'Der Zugang konnte nicht gespeichert werden.');
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword(account: Account) {
    if (!client?.id || !account.id || busy) return;
    if (!window.confirm(`Passwort für ${account.email} neu vergeben?`)) return;
    setBusy(true);
    setError('');
    try {
      const result: any = await api(`clients/${client.id}/portal-users/${account.id}/reset-password/`, {
        method: 'POST', body: '{}',
      });
      setCredentials({ email: result.email, temporary_password: result.temporary_password });
      setNotice('Neues Passwort wurde erstellt.');
    } catch (err: any) {
      setError(err?.message || 'Passwort konnte nicht zurückgesetzt werden.');
    } finally {
      setBusy(false);
    }
  }

  async function setActive(account: Account, active: boolean) {
    if (!client?.id || !account.id || busy) return;
    if (!window.confirm(active ? 'Diesen Zugang wieder aktivieren?' : 'Diesen Zugang sperren?')) return;
    setBusy(true);
    setError('');
    try {
      await api(`clients/${client.id}/portal-users/${account.id}/`, {
        method: 'PATCH', body: JSON.stringify({ ...account, is_active: active }),
      });
      await refresh(client.id);
      setNotice(active ? 'Zugang aktiviert.' : 'Zugang gesperrt.');
    } catch (err: any) {
      setError(err?.message || 'Status konnte nicht geändert werden.');
    } finally {
      setBusy(false);
    }
  }

  return <IonModal isOpen={!!client} onDidDismiss={onClose} className="client-account-modal">
    <IonContent className="ion-padding">
      <section className="client-account-manager">
        <header>
          <div><small>KUNDENPORTAL</small><h2>Zugänge für {client?.name}</h2><p>Für einen bestehenden Kunden einzelne Logins mit eigenen Rechten verwalten.</p></div>
          <IonButton fill="clear" onClick={onClose}>Schließen</IonButton>
        </header>
        {error && <div className="client-account-error" role="alert">{error}</div>}
        {notice && <div className="client-account-success">{notice}</div>}
        {credentials && <div className="client-account-secret">
          <b>Temporäre Zugangsdaten</b>
          <p>Das Passwort wird nur jetzt angezeigt. Bitte sicher an die Person weitergeben.</p>
          <code>{credentials.email}</code><code>{credentials.temporary_password}</code>
          <IonButton size="small" fill="outline" onClick={() => navigator.clipboard?.writeText(`${credentials.email}\n${credentials.temporary_password}`)}>Zugangsdaten kopieren</IonButton>
          <IonButton size="small" fill="clear" onClick={() => setCredentials(null)}>Ausblenden</IonButton>
        </div>}
        {!editing ? <>
          <div className="client-account-toolbar"><b>{accounts.length} Kundenzugänge</b><IonButton onClick={newAccount}>Neuen Zugang anlegen</IonButton></div>
          {accounts.map((account) => <div className="client-account-row" key={account.id}>
            <div><b>{account.first_name} {account.last_name}</b><p>{account.email}</p><small>{account.is_active ? 'Aktiv' : 'Gesperrt'} · {account.read_only ? 'Nur Dienstplan' : 'Vollzugriff'}</small></div>
            <div className="client-account-actions">
              <IonButton size="small" fill="outline" disabled={busy} onClick={() => choose(account)}>Rechte</IonButton>
              <IonButton size="small" fill="clear" disabled={busy} onClick={() => void resetPassword(account)}>Passwort</IonButton>
              <IonButton size="small" fill="clear" color={account.is_active ? 'danger' : 'success'} disabled={busy} onClick={() => void setActive(account, !account.is_active)}>{account.is_active ? 'Sperren' : 'Aktivieren'}</IonButton>
            </div>
          </div>)}
          {!accounts.length && <p>Für diesen Kunden sind noch keine Zugänge angelegt.</p>}
        </> : <div className="client-account-form">
          <h3>{form.id ? 'Zugang bearbeiten' : 'Neuen Kundenzugang erstellen'}</h3>
          <div className="client-account-fields">
            <label>Vorname <input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} /></label>
            <label>Nachname <input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} /></label>
            <label>E Mail Adresse <input type="email" disabled={!!form.id} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
            <label>Zugriffsart <select value={form.read_only ? 'schedule' : 'full'} onChange={(e) => setForm({
              ...form, read_only: e.target.value === 'schedule',
              location_scope_id: e.target.value === 'schedule' ? (allowedLocations.length === 1 ? allowedLocations[0].id : '') : '',
              position_ids: [],
            })}>
              <option value="schedule">Nur Dienstplan ansehen</option>
              <option value="full">Vollzugriff auf das Kundenportal</option>
            </select></label>
          </div>
          {form.read_only ? <>
            <label className="client-account-wide">Standort <select value={form.location_scope_id} onChange={(e) => setForm({ ...form, location_scope_id: e.target.value })}>
              <option value="">Standort auswählen</option>
              {allowedLocations.map((loc) => <option value={loc.id} key={loc.id}>{loc.name}</option>)}
            </select></label>
            <div className="client-account-positions"><b>Freigegebene Bereiche</b><small>Ohne Auswahl sind alle Bereiche am gewählten Standort sichtbar.</small>
              {allowedPositions.map((pos) => <label key={pos.id}><input type="checkbox" checked={form.position_ids.includes(pos.id)} onChange={(e) => togglePosition(pos.id, e.target.checked)} /> {pos.name}</label>)}
            </div>
            <p className="client-account-info">Dieser Zugang kann nur die freigegebenen Schichten lesen. Aufträge, Verträge, Personalverwaltung und andere Bereiche bleiben gesperrt.</p>
          </> : <p className="client-account-info">Vollzugriff zeigt alle Bereiche und Standorte dieses Kunden und erlaubt Aktionen im Kundenportal. Für eingeschränkte Abteilungen bitte „Nur Dienstplan ansehen“ auswählen.</p>}
          <div className="client-account-buttons"><IonButton fill="outline" disabled={busy} onClick={() => setEditing(false)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={() => void save()}>{busy ? <IonSpinner /> : 'Speichern'}</IonButton></div>
        </div>}
      </section>
    </IonContent>
  </IonModal>;
}

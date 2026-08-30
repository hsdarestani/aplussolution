import React, { useEffect, useMemo, useState } from 'react';
import { IonAlert, IonBadge, IonButton, IonIcon, IonSearchbar, IonToast } from '@ionic/react';
import { copyOutline, mailOutline, personAddOutline, refreshOutline } from 'ionicons/icons';
import { api } from './api';
import MasterDataQuickPanel from './MasterDataQuickPanel';
import './employee-portal.css';

const label: any = { active: 'Aktiv', invited: 'Einladung offen', not_activated: 'Nicht aktiviert', missing_email: 'E-Mail fehlt' };
const color: any = { active: 'success', invited: 'primary', not_activated: 'warning', missing_email: 'danger' };
const isSyntheticMigrationRow = (row: any) => String(row?.email || '').toLowerCase().endsWith('@sync.invalid');

export default function PortalAccessPanel() {
  const [rows, setRows] = useState<any[]>([]);
  const [search, setSearch] = useState('');
  const [toast, setToast] = useState('');
  const [busy, setBusy] = useState('');
  const [confirmBulk, setConfirmBulk] = useState(false);

  async function load() {
    const result: any[] = await api(`workers/portal-status/?search=${encodeURIComponent(search)}`);
    setRows((result || []).filter(row => !isSyntheticMigrationRow(row)));
  }

  useEffect(() => { void load(); }, []);

  const counts = useMemo(() => rows.reduce((acc: any, row: any) => {
    acc[row.state] = (acc[row.state] || 0) + 1;
    return acc;
  }, {}), [rows]);

  const bulkRows = useMemo(() => rows.filter((row: any) => row.state !== 'active' && row.state !== 'missing_email'), [rows]);
  const bulkEligible = bulkRows.length;

  async function invite(row: any) {
    setBusy(row.worker_id);
    try {
      const result: any = await api(`workers/${row.worker_id}/invite/`, { method: 'POST', body: '{}' });
      if (!result.activation_url) throw new Error('Aktivierungslink konnte nicht erstellt werden.');
      await navigator.clipboard?.writeText(result.activation_url);
      setToast(result.delivered
        ? 'Einladung wurde per E-Mail versendet. Aktivierungslink wurde zusätzlich kopiert.'
        : 'Aktivierungslink wurde erstellt und in die Zwischenablage kopiert.');
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy('');
    }
  }

  async function bulk() {
    const workerIds = bulkRows.map((row: any) => row.worker_id).filter(Boolean);
    if (!workerIds.length) return;
    setBusy('bulk');
    try {
      const result: any = await api('workers/bulk-invite/', { method: 'POST', body: JSON.stringify({ worker_ids: workerIds }) });
      const links = (result.results || [])
        .filter((item: any) => item.activation_url && !String(item.email || '').toLowerCase().endsWith('@sync.invalid'))
        .map((item: any) => `${item.email}: ${item.activation_url}`)
        .join('\n');
      if (links) {
        await navigator.clipboard?.writeText(links);
        setToast(`${result.count} Einladung(en) erstellt. Aktivierungslinks wurden kopiert.`);
      } else {
        setToast(`${result.count} Einladung(en) verarbeitet.`);
      }
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy('');
    }
  }

  return <>
    <MasterDataQuickPanel />

    <section className="portal-access-panel">
      <div className="portal-access-head">
        <div>
          <small>MITARBEITERPORTAL</small>
          <h2>Zugänge & Aktivierung</h2>
          <p>Mitarbeiter aktivieren ihren eigenen A+ Workforce Zugang. Keine Passwörter werden von der Disposition vergeben.</p>
        </div>
        <IonButton fill="outline" disabled={!!busy || bulkEligible === 0} onClick={() => setConfirmBulk(true)}>
          <IonIcon slot="start" icon={personAddOutline} />Offene Einladungen erstellen
        </IonButton>
      </div>

      <div className="portal-access-stats">
        <span><b>{counts.active || 0}</b> aktiv</span>
        <span><b>{counts.invited || 0}</b> eingeladen</span>
        <span><b>{counts.not_activated || 0}</b> nicht aktiviert</span>
        <span><b>{counts.missing_email || 0}</b> ohne E-Mail</span>
      </div>

      <div className="portal-search">
        <IonSearchbar value={search} debounce={350} placeholder="Mitarbeiter, E-Mail oder Personalnummer suchen …" onIonInput={event => setSearch(String(event.detail.value || ''))} onIonChange={() => void load()} />
        <IonButton fill="clear" onClick={() => void load()}><IonIcon slot="icon-only" icon={refreshOutline} /></IonButton>
      </div>

      <div className="portal-access-list">
        {rows.map(row => <div className="portal-access-row" key={row.worker_id}>
          <div className="portal-person"><span>{String(row.name || 'M')[0].toUpperCase()}</span><div><b>{row.name}</b><p>{row.email}</p></div></div>
          <IonBadge color={color[row.state] || 'medium'}>{label[row.state] || row.state}</IonBadge>
          {row.state !== 'active' && row.state !== 'missing_email' && <IonButton size="small" fill="outline" disabled={!!busy} onClick={() => invite(row)}>
            <IonIcon slot="start" icon={row.state === 'invited' ? copyOutline : mailOutline} />{row.state === 'invited' ? 'Neu senden & Link kopieren' : 'Einladen & Link kopieren'}
          </IonButton>}
        </div>)}
      </div>
    </section>

    <IonAlert
      isOpen={confirmBulk}
      onDidDismiss={() => setConfirmBulk(false)}
      header="Offene Einladungen wirklich erstellen?"
      message={`Für ${bulkEligible} aktuell angezeigte Mitarbeiter werden Aktivierungen verarbeitet. Bereits aktive Zugänge, fehlende E-Mail-Adressen und Migrationsdatensätze bleiben unberührt.`}
      buttons={[
        { text: 'Abbrechen', role: 'cancel' },
        { text: 'Einladungen erstellen', handler: () => { setConfirmBulk(false); void bulk(); } },
      ]}
    />
    <IonToast isOpen={!!toast} message={toast} duration={1000} onDidDismiss={() => setToast('')} />
  </>;
}

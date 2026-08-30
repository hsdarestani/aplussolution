import React, { useEffect, useMemo, useState } from 'react';
import {
  IonBadge,
  IonButton,
  IonIcon,
  IonInput,
  IonItem,
  IonLabel,
  IonModal,
  IonSearchbar,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonToast,
  IonToggle,
} from '@ionic/react';
import {
  briefcaseOutline,
  checkmarkCircleOutline,
  chevronDownOutline,
  chevronUpOutline,
  closeCircleOutline,
  createOutline,
  locationOutline,
  refreshOutline,
} from 'ionicons/icons';
import { api } from './api';
import './masterdata-quick.css';

const unpack = (data: any): any[] => data?.results || data || [];
const value = (event: any) => event.detail.value ?? '';
const timestamp = (item: any) => new Date(item?.created_at || item?.updated_at || 0).getTime();

export default function MasterDataQuickPanel() {
  const [clients, setClients] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [modal, setModal] = useState<'location' | 'position' | ''>('');
  const [editing, setEditing] = useState<any>();
  const [locationForm, setLocationForm] = useState<any>({ geofence_radius_m: 250, active: true });
  const [positionForm, setPositionForm] = useState<any>({ color: '#155eef', active: true });
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState('');
  const [query, setQuery] = useState('');
  const [showAllLocations, setShowAllLocations] = useState(false);
  const [showAllPositions, setShowAllPositions] = useState(false);
  const [highlightId, setHighlightId] = useState('');

  async function load() {
    setLoading(true);
    try {
      const [clientData, locationData, positionData] = await Promise.all([
        api('clients/?ordering=name'),
        api('locations/'),
        api('positions/'),
      ]);
      setClients(unpack(clientData));
      setLocations(unpack(locationData).sort((a, b) => timestamp(b) - timestamp(a)));
      setPositions(unpack(positionData).sort((a, b) => timestamp(b) - timestamp(a)));
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const filteredLocations = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return locations;
    return locations.filter((item) => `${item.name || ''} ${item.client_name || ''} ${item.address || ''}`.toLowerCase().includes(needle));
  }, [locations, query]);

  const filteredPositions = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return positions;
    return positions.filter((item) => String(item.name || '').toLowerCase().includes(needle));
  }, [positions, query]);

  const visibleLocations = (showAllLocations || query ? filteredLocations : filteredLocations.slice(0, 6));
  const visiblePositions = (showAllPositions || query ? filteredPositions : filteredPositions.slice(0, 6));

  function flash(id?: string) {
    if (!id) return;
    setHighlightId(id);
    window.setTimeout(() => setHighlightId(''), 3500);
  }

  function openLocation(item?: any) {
    setEditing(item);
    setLocationForm(item ? {
      client: item.client || '',
      name: item.name || '',
      address: item.address || '',
      geofence_radius_m: item.geofence_radius_m || 250,
      active: item.active !== false,
    } : { geofence_radius_m: 250, active: true });
    setModal('location');
  }

  function openPosition(item?: any) {
    setEditing(item);
    setPositionForm(item ? {
      name: item.name || '',
      color: item.color || '#155eef',
      active: item.active !== false,
    } : { color: '#155eef', active: true });
    setModal('position');
  }

  async function saveLocation() {
    if (!String(locationForm.name || '').trim() || !String(locationForm.address || '').trim()) {
      setToast('Bitte Bezeichnung und Adresse ausfüllen.');
      return;
    }
    setBusy(true);
    try {
      const payload = {
        ...locationForm,
        client: locationForm.client || null,
        geofence_radius_m: Number(locationForm.geofence_radius_m || 250),
      };
      const result: any = await api(editing ? `locations/${editing.id}/` : 'locations/', {
        method: editing ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      });
      setToast(editing ? 'Einsatzort wurde aktualisiert.' : 'Einsatzort wurde angelegt und oben einsortiert.');
      setModal('');
      setEditing(undefined);
      await load();
      flash(result?.id);
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function savePosition() {
    if (!String(positionForm.name || '').trim()) {
      setToast('Bitte eine Bezeichnung eingeben.');
      return;
    }
    setBusy(true);
    try {
      const result: any = await api(editing ? `positions/${editing.id}/` : 'positions/', {
        method: editing ? 'PATCH' : 'POST',
        body: JSON.stringify(positionForm),
      });
      setToast(editing ? 'Position wurde aktualisiert.' : 'Position wurde angelegt und oben einsortiert.');
      setModal('');
      setEditing(undefined);
      await load();
      flash(result?.id);
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(kind: 'locations' | 'positions', item: any) {
    setBusy(true);
    try {
      await api(`${kind}/${item.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ active: item.active === false }),
      });
      setToast(item.active === false ? 'Stammdatensatz wurde aktiviert.' : 'Stammdatensatz wurde deaktiviert.');
      await load();
      flash(item.id);
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  return <>
    <section className="masterdata-quick-panel" data-testid="masterdata-quick-panel">
      <div className="masterdata-quick-head">
        <div>
          <small>STAMMDATEN</small>
          <h2>Einsatzorte & Positionen</h2>
          <p>Neu angelegte Einträge erscheinen sofort ganz oben und stehen direkt in Dienstplanung und Aufträgen bereit.</p>
        </div>
        <IonButton fill="clear" disabled={loading || busy} onClick={() => void load()} aria-label="Stammdaten aktualisieren"><IonIcon slot="icon-only" icon={refreshOutline} /></IonButton>
      </div>

      <div className="masterdata-create-actions">
        <IonButton onClick={() => openLocation()}><IonIcon slot="start" icon={locationOutline} />Einsatzort anlegen</IonButton>
        <IonButton fill="outline" onClick={() => openPosition()}><IonIcon slot="start" icon={briefcaseOutline} />Position anlegen</IonButton>
      </div>

      <IonSearchbar className="masterdata-search" value={query} debounce={200} placeholder="Einsatzort oder Position suchen …" onIonInput={(event) => setQuery(String(event.detail.value || ''))} />

      {loading ? <div className="masterdata-loading"><IonSpinner /><span>Stammdaten werden geladen …</span></div> : <div className="masterdata-quick-grid">
        <div className="masterdata-card">
          <div className="masterdata-card-title"><div><IonIcon icon={locationOutline} /><div><b>Einsatzorte</b><span>{locations.filter(item => item.active !== false).length} aktiv · {locations.length} gesamt</span></div></div></div>
          <div className="masterdata-list">
            {visibleLocations.map(item => <div className={`masterdata-row ${item.active === false ? 'inactive' : ''} ${highlightId === item.id ? 'just-created' : ''}`} key={item.id}>
              <div className="masterdata-main"><b>{item.name}</b><span>{item.client_name || 'Ohne Kunde'} · {item.address}</span></div>
              <IonBadge color={item.active === false ? 'medium' : 'success'}>{item.active === false ? 'Inaktiv' : 'Aktiv'}</IonBadge>
              <div className="masterdata-row-actions">
                <IonButton size="small" fill="clear" onClick={() => openLocation(item)} aria-label={`${item.name} bearbeiten`}><IonIcon slot="icon-only" icon={createOutline} /></IonButton>
                <IonButton size="small" fill="clear" color={item.active === false ? 'success' : 'medium'} disabled={busy} onClick={() => void toggle('locations', item)} aria-label={`${item.name} ${item.active === false ? 'aktivieren' : 'deaktivieren'}`}><IonIcon slot="icon-only" icon={item.active === false ? checkmarkCircleOutline : closeCircleOutline} /></IonButton>
              </div>
            </div>)}
            {!visibleLocations.length && <div className="masterdata-empty">Kein passender Einsatzort gefunden.</div>}
          </div>
          {!query && filteredLocations.length > 6 && <IonButton className="masterdata-show-all" fill="clear" size="small" onClick={() => setShowAllLocations(!showAllLocations)}><IonIcon slot="start" icon={showAllLocations ? chevronUpOutline : chevronDownOutline} />{showAllLocations ? 'Weniger anzeigen' : `Alle ${filteredLocations.length} anzeigen`}</IonButton>}
        </div>

        <div className="masterdata-card">
          <div className="masterdata-card-title"><div><IonIcon icon={briefcaseOutline} /><div><b>Positionen</b><span>{positions.filter(item => item.active !== false).length} aktiv · {positions.length} gesamt</span></div></div></div>
          <div className="masterdata-list">
            {visiblePositions.map(item => <div className={`masterdata-row ${item.active === false ? 'inactive' : ''} ${highlightId === item.id ? 'just-created' : ''}`} key={item.id}>
              <div className="masterdata-main position"><i style={{ background: item.color || '#155eef' }} /><b>{item.name}</b></div>
              <IonBadge color={item.active === false ? 'medium' : 'success'}>{item.active === false ? 'Inaktiv' : 'Aktiv'}</IonBadge>
              <div className="masterdata-row-actions">
                <IonButton size="small" fill="clear" onClick={() => openPosition(item)} aria-label={`${item.name} bearbeiten`}><IonIcon slot="icon-only" icon={createOutline} /></IonButton>
                <IonButton size="small" fill="clear" color={item.active === false ? 'success' : 'medium'} disabled={busy} onClick={() => void toggle('positions', item)} aria-label={`${item.name} ${item.active === false ? 'aktivieren' : 'deaktivieren'}`}><IonIcon slot="icon-only" icon={item.active === false ? checkmarkCircleOutline : closeCircleOutline} /></IonButton>
              </div>
            </div>)}
            {!visiblePositions.length && <div className="masterdata-empty">Keine passende Position gefunden.</div>}
          </div>
          {!query && filteredPositions.length > 6 && <IonButton className="masterdata-show-all" fill="clear" size="small" onClick={() => setShowAllPositions(!showAllPositions)}><IonIcon slot="start" icon={showAllPositions ? chevronUpOutline : chevronDownOutline} />{showAllPositions ? 'Weniger anzeigen' : `Alle ${filteredPositions.length} anzeigen`}</IonButton>}
        </div>
      </div>}
    </section>

    <IonModal isOpen={modal === 'location'} onDidDismiss={() => { setModal(''); setEditing(undefined); }}>
      <div className="masterdata-modal">
        <div className="masterdata-modal-head"><div><small>STAMMDATEN</small><h2>{editing ? 'Einsatzort bearbeiten' : 'Einsatzort anlegen'}</h2></div><IonButton fill="clear" onClick={() => { setModal(''); setEditing(undefined); }}>Schließen</IonButton></div>
        <div className="masterdata-form">
          <IonSelect fill="outline" label="Kunde" labelPlacement="floating" value={locationForm.client || ''} onIonChange={event => setLocationForm({ ...locationForm, client: value(event) })}>
            <IonSelectOption value="">Ohne feste Zuordnung</IonSelectOption>
            {clients.filter(client => client.active !== false).map(client => <IonSelectOption value={client.id} key={client.id}>{client.name}</IonSelectOption>)}
          </IonSelect>
          <IonInput fill="outline" label="Bezeichnung *" labelPlacement="floating" value={locationForm.name || ''} onIonInput={event => setLocationForm({ ...locationForm, name: value(event) })} />
          <IonTextarea className="full" fill="outline" label="Adresse *" labelPlacement="floating" value={locationForm.address || ''} onIonInput={event => setLocationForm({ ...locationForm, address: value(event) })} />
          <IonInput fill="outline" type="number" min="1" label="Geofence-Radius (m)" labelPlacement="floating" value={locationForm.geofence_radius_m || 250} onIonInput={event => setLocationForm({ ...locationForm, geofence_radius_m: value(event) })} />
          <IonItem lines="none" className="masterdata-toggle"><IonLabel>Aktiv</IonLabel><IonToggle checked={locationForm.active !== false} onIonChange={event => setLocationForm({ ...locationForm, active: event.detail.checked })} /></IonItem>
        </div>
        <div className="masterdata-modal-actions"><IonButton fill="outline" onClick={() => { setModal(''); setEditing(undefined); }}>Abbrechen</IonButton><IonButton disabled={busy} onClick={() => void saveLocation()}>{busy ? <IonSpinner name="dots" /> : 'Speichern'}</IonButton></div>
      </div>
    </IonModal>

    <IonModal isOpen={modal === 'position'} onDidDismiss={() => { setModal(''); setEditing(undefined); }}>
      <div className="masterdata-modal compact">
        <div className="masterdata-modal-head"><div><small>STAMMDATEN</small><h2>{editing ? 'Position bearbeiten' : 'Position anlegen'}</h2></div><IonButton fill="clear" onClick={() => { setModal(''); setEditing(undefined); }}>Schließen</IonButton></div>
        <div className="masterdata-form one-column">
          <IonInput fill="outline" label="Bezeichnung *" labelPlacement="floating" value={positionForm.name || ''} onIonInput={event => setPositionForm({ ...positionForm, name: value(event) })} />
          <label className="color-picker-field">
            <span>Farbe</span>
            <div className="color-picker-control">
              <input aria-label="Farbe auswählen" type="color" value={positionForm.color || '#155eef'} onChange={event => setPositionForm({ ...positionForm, color: event.target.value })} />
              <b style={{ background: positionForm.color || '#155eef' }} />
              <em>Farbe auswählen</em>
            </div>
          </label>
          <IonItem lines="none" className="masterdata-toggle"><IonLabel>Aktiv</IonLabel><IonToggle checked={positionForm.active !== false} onIonChange={event => setPositionForm({ ...positionForm, active: event.detail.checked })} /></IonItem>
        </div>
        <div className="masterdata-modal-actions"><IonButton fill="outline" onClick={() => { setModal(''); setEditing(undefined); }}>Abbrechen</IonButton><IonButton disabled={busy} onClick={() => void savePosition()}>{busy ? <IonSpinner name="dots" /> : 'Speichern'}</IonButton></div>
      </div>
    </IonModal>

    <IonToast isOpen={!!toast} message={toast} duration={1000} onDidDismiss={() => setToast('')} />
  </>;
}

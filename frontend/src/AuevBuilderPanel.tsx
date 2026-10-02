import React, { useEffect, useMemo, useState } from 'react';
import {
  IonBadge,
  IonButton,
  IonContent,
  IonInput,
  IonModal,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonToast,
} from '@ionic/react';
import { api } from './api';

type Props = {
  clients: any[];
  onChanged?: () => void | Promise<void>;
};

const localDateInput = (date: Date) =>
  new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Europe/Berlin',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);

const deDate = (value?: string) => {
  if (!value) return '–';
  const [year, month, day] = value.slice(0, 10).split('-');
  return year && month && day ? `${day}.${month}.${year}` : value;
};

const apiRows = (data: any) => data?.results || data || [];

export default function AuevBuilderPanel({ clients, onChanged }: Props) {
  const [clientId, setClientId] = useState('');
  const [start, setStart] = useState(() => {
    const value = new Date();
    value.setDate(value.getDate() - 7);
    return localDateInput(value);
  });
  const [end, setEnd] = useState(() => {
    const value = new Date();
    value.setDate(value.getDate() + 35);
    return localDateInput(value);
  });
  const [templateKey, setTemplateKey] = useState<'classic' | 'new'>('classic');
  const [signatureDate, setSignatureDate] = useState('');
  const [sequenceNumber, setSequenceNumber] = useState('');
  const [preview, setPreview] = useState<any>();
  const [exports, setExports] = useState<any[]>([]);
  const [busy, setBusy] = useState('');
  const [toast, setToast] = useState('');

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsClient, setSettingsClient] = useState('');
  const [settingsForm, setSettingsForm] = useState<any>({});
  const [settingsDefaults, setSettingsDefaults] = useState<any>({});
  const [editOpen, setEditOpen] = useState(false);
  const [editItem, setEditItem] = useState<any>();
  const [editForm, setEditForm] = useState<any>({});

  const loadExports = async () => {
    const data = await api('automation/auev-exports/');
    setExports(apiRows(data));
  };

  useEffect(() => {
    void loadExports().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!clientId || !start || !end) {
      setPreview(undefined);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        const query = new URLSearchParams({ client_id: clientId, start, end });
        const result: any = await api(`automation/auev-builder/preview/?${query.toString()}`);
        setPreview(result);
        setSignatureDate(result.signature_date_default || '');
        setSequenceNumber(String(result.sequence_number || ''));
      } catch (reason: any) {
        setPreview(undefined);
        setToast(reason.message);
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [clientId, start, end]);

  const blockers = useMemo(() => {
    const result: string[] = [];
    if (!preview?.row_count) result.push('Keine besetzten Einsätze im gewählten Zeitraum.');
    if (preview?.missing_birth_dates?.length) result.push(`Geburtsdatum fehlt für ${preview.missing_birth_dates.join(', ')}.`);
    if (templateKey === 'new' && preview?.new_template_limit_exceeded) result.push('Die neue Vorlage unterstützt maximal 25 Mitarbeiterzeilen.');
    return result;
  }, [preview, templateKey]);

  const assignmentWarning = preview?.unassigned?.length
    ? `${preview.unassigned.length} Einsatz oder Einsätze sind noch nicht vollständig besetzt. Dafür werden leere Mitarbeiterzeilen ausgegeben.`
    : '';

  async function generate() {
    if (!clientId || !start || !end || !signatureDate || blockers.length) return;
    setBusy('generate');
    try {
      const result: any = await api('automation/auev-builder/generate/', {
        method: 'POST',
        body: JSON.stringify({
          client_id: clientId,
          start,
          end,
          template_key: templateKey,
          signature_date: signatureDate,
          sequence_number: sequenceNumber || null,
        }),
      });
      setToast(`${result.file_stem} wurde als PDF und DOCX erstellt.`);
      await loadExports();
      if (onChanged) await onChanged();
      const query = new URLSearchParams({ client_id: clientId, start, end });
      const next: any = await api(`automation/auev-builder/preview/?${query.toString()}`);
      setPreview(next);
      setSignatureDate(next.signature_date_default || '');
      setSequenceNumber(String(next.sequence_number || ''));
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy('');
    }
  }

  function openEdit(item: any) {
    setEditItem(item);
    setEditForm({
      client_id: item.client_id,
      start: item.date_from,
      end: item.date_to,
      template_key: item.template_key,
      signature_date: item.signature_date,
      sequence_number: item.sequence_number,
    });
    setEditOpen(true);
  }

  async function saveEdit() {
    if (!editItem) return;
    setBusy('edit');
    try {
      const updated: any = await api(`automation/auev-exports/${editItem.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({
          client_id: editForm.client_id,
          start: editForm.start,
          end: editForm.end,
          template_key: editForm.template_key,
          signature_date: editForm.signature_date,
          sequence_number: editForm.sequence_number,
        }),
      });
      setEditOpen(false);
      setEditItem(undefined);
      setToast(`${updated.file_stem} wurde aktualisiert und neu erzeugt.`);
      await loadExports();
      if (onChanged) await onChanged();
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy('');
    }
  }

  async function removeExport(item: any) {
    if (!window.confirm(`${item.file_stem} wirklich löschen? PDF und DOCX werden ebenfalls gelöscht.`)) return;
    setBusy(`delete-${item.id}`);
    try {
      await api(`automation/auev-exports/${item.id}/`, { method: 'DELETE' });
      setToast('ANÜ Datei wurde gelöscht.');
      await loadExports();
      if (onChanged) await onChanged();
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy('');
    }
  }

  async function loadSettings(targetClient = '') {
    const query = targetClient ? `?client_id=${encodeURIComponent(targetClient)}` : '';
    const result: any = await api(`automation/auev-settings/${query}`);
    setSettingsDefaults(result.defaults || {});
    setSettingsForm(result.overrides || {});
  }

  async function openSettings() {
    setSettingsClient(clientId || '');
    setSettingsOpen(true);
    try {
      await loadSettings(clientId || '');
    } catch (reason: any) {
      setToast(reason.message);
    }
  }

  async function saveSettings() {
    setBusy('settings');
    try {
      await api('automation/auev-settings/', {
        method: 'PATCH',
        body: JSON.stringify({
          client_id: settingsClient || null,
          permit_date: settingsForm.permit_date || '',
          framework_date: settingsForm.framework_date || '',
          effective_date: settingsForm.effective_date || '',
          required_qualification: settingsForm.required_qualification || '',
          intended_activity: settingsForm.intended_activity || '',
          client_contract_text: settingsForm.client_contract_text || '',
          file_label: settingsForm.file_label || '',
          last_sequence_number: settingsClient ? Number(settingsForm.last_sequence_number || 0) : undefined,
        }),
      });
      setSettingsOpen(false);
      setToast(settingsClient ? 'ANÜ Einstellungen für den Kunden gespeichert.' : 'ANÜ Standardwerte gespeichert.');
      if (clientId && start && end) {
        const query = new URLSearchParams({ client_id: clientId, start, end });
        const next: any = await api(`automation/auev-builder/preview/?${query.toString()}`);
        setPreview(next);
        setSequenceNumber(String(next.sequence_number || ''));
      }
    } catch (reason: any) {
      setToast(reason.message);
    } finally {
      setBusy('');
    }
  }

  return (
    <>
      <section className="panel auev-builder-panel" data-testid="auev-builder-panel">
        <div className="auev-builder-head">
          <div>
            <small>ANÜ DATEIGENERATOR</small>
            <h3>Ein Vertragspaket aus einem gewählten Zeitraum</h3>
            <p>Du wählst Kunde, Zeitraum und Vorlage. Das System nimmt die besetzten Einsätze aus A+ Workforce und erstellt genau eine DOCX Datei und eine PDF Datei.</p>
          </div>
          <IonButton fill="outline" onClick={() => void openSettings()}>ANÜ Einstellungen</IonButton>
        </div>

        <div className="auev-builder-form">
          <IonSelect
            fill="outline"
            label="Kunde"
            labelPlacement="floating"
            value={clientId}
            onIonChange={(event) => setClientId(String(event.detail.value || ''))}
          >
            <IonSelectOption value="">Kunde auswählen</IonSelectOption>
            {clients.map((client) => <IonSelectOption value={client.id} key={client.id}>{client.name}</IonSelectOption>)}
          </IonSelect>

          <IonInput
            fill="outline"
            type="date"
            label="Von"
            labelPlacement="floating"
            value={start}
            onIonInput={(event) => setStart(String(event.detail.value || ''))}
          />
          <IonInput
            fill="outline"
            type="date"
            label="Bis"
            labelPlacement="floating"
            value={end}
            onIonInput={(event) => setEnd(String(event.detail.value || ''))}
          />

          <IonSelect
            fill="outline"
            label="Vorlage"
            labelPlacement="floating"
            value={templateKey}
            onIonChange={(event) => setTemplateKey(event.detail.value as 'classic' | 'new')}
          >
            <IonSelectOption value="classic">Klassisch wie bisherige ANÜ Dateien</IonSelectOption>
            <IonSelectOption value="new">Neue Vorlage new templ</IonSelectOption>
          </IonSelect>

          <IonInput
            fill="outline"
            type="date"
            label="Unterschriftsdatum"
            labelPlacement="floating"
            value={signatureDate}
            onIonInput={(event) => setSignatureDate(String(event.detail.value || ''))}
          />

          <IonInput
            fill="outline"
            type="number"
            min="1"
            label="Dokumentnummer"
            labelPlacement="floating"
            value={sequenceNumber}
            onIonInput={(event) => setSequenceNumber(String(event.detail.value || ''))}
          />
        </div>

        {preview && (
          <div className="auev-preview">
            <div><small>Dateiname</small><strong>{preview.file_stem}</strong></div>
            <div><small>Kalenderwochen</small><strong>{(preview.calendar_weeks || []).map((week: number) => `KW${week}`).join(' · ') || '–'}</strong></div>
            <div><small>Erster Einsatz</small><strong>{deDate(preview.first_shift_date)}</strong></div>
            <div><small>Letzter Einsatz</small><strong>{deDate(preview.last_shift_date)}</strong></div>
            <div><small>Einsätze</small><strong>{preview.shift_count || 0}</strong></div>
            <div><small>Mitarbeiterzeilen</small><strong>{preview.row_count || 0}</strong></div>
          </div>
        )}

        {!!assignmentWarning && (
          <div className="auev-warning">
            <p>{assignmentWarning}</p>
          </div>
        )}

        {!!blockers.length && (
          <div className="auev-blockers">
            {blockers.map((item) => <p key={item}>{item}</p>)}
          </div>
        )}

        <div className="auev-generate-row">
          <p>Das Befristungsdatum wird automatisch aus dem letzten Einsatz übernommen. Das Unterschriftsdatum wird zunächst zwei Tage vor dem ersten Einsatz vorgeschlagen und bleibt editierbar.</p>
          <IonButton disabled={!preview || !!blockers.length || !!busy} onClick={() => void generate()}>
            {busy === 'generate' ? <IonSpinner name="dots" /> : 'PDF + DOCX erstellen'}
          </IonButton>
        </div>
      </section>

      <section className="panel auev-export-history">
        <div className="section-head">
          <div>
            <h3>Erstellte ANÜ Dateien</h3>
            <p>Eine Zeile entspricht einem erzeugten Vertragspaket, nicht einem einzelnen Einsatz.</p>
          </div>
        </div>
        <div className="auev-export-table">
          <div className="auev-export-row auev-export-header">
            <span>Datei</span><span>Kunde</span><span>Zeitraum</span><span>Vorlage</span><span>Dateien & Aktionen</span>
          </div>
          {exports.map((item) => (
            <div className="auev-export-row" key={item.id}>
              <div><b>{item.file_stem}</b><small>{item.row_count} Mitarbeiterzeilen</small></div>
              <span>{item.client_name}</span>
              <span>{deDate(item.first_shift_date)} bis {deDate(item.last_shift_date)}</span>
              <IonBadge>{item.template_label}</IonBadge>
              <div className="auev-file-actions">
                <IonButton size="small" fill="outline" href={item.pdf_url} target="_blank">PDF</IonButton>
                <IonButton size="small" fill="outline" href={item.docx_url} target="_blank">DOCX</IonButton>
                <IonButton size="small" fill="outline" onClick={() => openEdit(item)}>Bearbeiten</IonButton>
                <IonButton
                  size="small"
                  fill="outline"
                  color="danger"
                  disabled={busy === `delete-${item.id}`}
                  onClick={() => void removeExport(item)}
                >
                  {busy === `delete-${item.id}` ? <IonSpinner name="dots" /> : 'Löschen'}
                </IonButton>
              </div>
            </div>
          ))}
          {!exports.length && <div className="empty">Noch keine ANÜ Dateien erzeugt.</div>}
        </div>
      </section>

      <IonModal isOpen={editOpen} onDidDismiss={() => setEditOpen(false)}>
        <IonContent className="ion-padding form">
          <div className="modal-head">
            <div>
              <small>ANÜ DATEI BEARBEITEN</small>
              <h2>{editItem?.file_stem || 'ANÜ Datei'}</h2>
              <p>Beim Speichern werden PDF und DOCX mit den neuen Werten neu erzeugt.</p>
            </div>
            <IonButton fill="clear" onClick={() => setEditOpen(false)}>Schließen</IonButton>
          </div>

          <div className="form-grid">
            <IonSelect
              fill="outline"
              label="Kunde"
              labelPlacement="floating"
              value={editForm.client_id || ''}
              onIonChange={(event) => setEditForm({ ...editForm, client_id: String(event.detail.value || '') })}
            >
              {clients.map((client) => <IonSelectOption value={client.id} key={client.id}>{client.name}</IonSelectOption>)}
            </IonSelect>

            <IonInput
              fill="outline"
              type="date"
              label="Von"
              labelPlacement="floating"
              value={editForm.start || ''}
              onIonInput={(event) => setEditForm({ ...editForm, start: String(event.detail.value || '') })}
            />

            <IonInput
              fill="outline"
              type="date"
              label="Bis"
              labelPlacement="floating"
              value={editForm.end || ''}
              onIonInput={(event) => setEditForm({ ...editForm, end: String(event.detail.value || '') })}
            />

            <IonSelect
              fill="outline"
              label="Vorlage"
              labelPlacement="floating"
              value={editForm.template_key || 'classic'}
              onIonChange={(event) => setEditForm({ ...editForm, template_key: event.detail.value })}
            >
              <IonSelectOption value="classic">Klassisch wie bisherige ANÜ Dateien</IonSelectOption>
              <IonSelectOption value="new">Neue Vorlage new templ</IonSelectOption>
            </IonSelect>

            <IonInput
              fill="outline"
              type="date"
              label="Unterschriftsdatum"
              labelPlacement="floating"
              value={editForm.signature_date || ''}
              onIonInput={(event) => setEditForm({ ...editForm, signature_date: String(event.detail.value || '') })}
            />

            <IonInput
              fill="outline"
              type="number"
              min="1"
              label="Dokumentnummer"
              labelPlacement="floating"
              value={editForm.sequence_number || ''}
              onIonInput={(event) => setEditForm({ ...editForm, sequence_number: String(event.detail.value || '') })}
            />
          </div>

          <div className="modal-actions">
            <IonButton fill="outline" onClick={() => setEditOpen(false)}>Abbrechen</IonButton>
            <IonButton disabled={busy === 'edit'} onClick={() => void saveEdit()}>
              {busy === 'edit' ? <IonSpinner name="dots" /> : 'Änderungen speichern'}
            </IonButton>
          </div>
        </IonContent>
      </IonModal>

      <IonModal isOpen={settingsOpen} onDidDismiss={() => setSettingsOpen(false)}>
        <IonContent className="ion-padding form">
          <div className="modal-head">
            <div>
              <small>ANÜ EINSTELLUNGEN</small>
              <h2>Standardwerte und Kundenwerte</h2>
            </div>
            <IonButton fill="clear" onClick={() => setSettingsOpen(false)}>Schließen</IonButton>
          </div>

          <div className="form-grid">
            <IonSelect
              fill="outline"
              label="Gültig für"
              labelPlacement="floating"
              value={settingsClient}
              onIonChange={(event) => {
                const value = String(event.detail.value || '');
                setSettingsClient(value);
                void loadSettings(value).catch((reason: any) => setToast(reason.message));
              }}
            >
              <IonSelectOption value="">Standard für alle Kunden</IonSelectOption>
              {clients.map((client) => <IonSelectOption value={client.id} key={client.id}>{client.name}</IonSelectOption>)}
            </IonSelect>

            {settingsClient && <div className="notice full">Leere Kundenfelder übernehmen automatisch den Standardwert.</div>}

            <IonInput fill="outline" type="date" label="Erlaubnisdatum" labelPlacement="floating" value={settingsForm.permit_date || ''} onIonInput={(event) => setSettingsForm({ ...settingsForm, permit_date: event.detail.value })} />
            <IonInput fill="outline" type="date" label="Datum der Rahmenvereinbarung" labelPlacement="floating" value={settingsForm.framework_date || ''} onIonInput={(event) => setSettingsForm({ ...settingsForm, framework_date: event.detail.value })} />
            <IonInput fill="outline" type="date" label="Wirkung zum" labelPlacement="floating" value={settingsForm.effective_date || ''} onIonInput={(event) => setSettingsForm({ ...settingsForm, effective_date: event.detail.value })} />
            <IonInput fill="outline" label="Erforderliche Qualifikation" labelPlacement="floating" value={settingsForm.required_qualification || ''} placeholder={settingsClient ? settingsDefaults.required_qualification || '' : ''} onIonInput={(event) => setSettingsForm({ ...settingsForm, required_qualification: event.detail.value })} />
            <IonInput fill="outline" label="Vorgesehene Tätigkeit" labelPlacement="floating" value={settingsForm.intended_activity || ''} placeholder={settingsClient ? settingsDefaults.intended_activity || '' : ''} onIonInput={(event) => setSettingsForm({ ...settingsForm, intended_activity: event.detail.value })} />
            <IonTextarea fill="outline" label="Vertragspartner Text" labelPlacement="floating" value={settingsForm.client_contract_text || ''} placeholder="Leer lassen für Kundenname plus Adresse aus Stammdaten" onIonInput={(event) => setSettingsForm({ ...settingsForm, client_contract_text: event.detail.value })} />
            <IonInput fill="outline" label="Kurzname für Dateinamen" labelPlacement="floating" value={settingsForm.file_label || ''} placeholder="Zum Beispiel Stadthaus am Markt" onIonInput={(event) => setSettingsForm({ ...settingsForm, file_label: event.detail.value })} />
            {settingsClient && <IonInput fill="outline" type="number" min="0" label="Letzte verwendete Dokumentnummer" labelPlacement="floating" value={settingsForm.last_sequence_number || 0} onIonInput={(event) => setSettingsForm({ ...settingsForm, last_sequence_number: event.detail.value })} />}
          </div>

          <div className="modal-actions">
            <IonButton fill="outline" onClick={() => setSettingsOpen(false)}>Abbrechen</IonButton>
            <IonButton disabled={busy === 'settings'} onClick={() => void saveSettings()}>
              {busy === 'settings' ? <IonSpinner name="dots" /> : 'Speichern'}
            </IonButton>
          </div>
        </IonContent>
      </IonModal>

      <IonToast isOpen={!!toast} message={toast} duration={1800} onDidDismiss={() => setToast('')} />
    </>
  );
}

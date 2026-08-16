import React, { useEffect, useMemo, useState } from 'react';
import {
  IonBadge,
  IonButton,
  IonCheckbox,
  IonIcon,
  IonInput,
  IonModal,
  IonSegment,
  IonSegmentButton,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonToggle,
} from '@ionic/react';
import { barChartOutline, closeOutline, cloudDownloadOutline, refreshOutline, saveOutline, timeOutline, trashOutline } from 'ionicons/icons';
import { api, User } from './api';
import './reporting-v8.css';

const API = String(import.meta.env.VITE_API_URL || 'http://localhost:8000/api').replace(/\/$/, '');
const unpack = (data: any): any[] => data?.results || data || [];
const eventValue = (event: any) => event.detail?.value ?? '';
const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (days: number) => {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
};
const display = (value: any) => {
  if (value == null || value === '') return '–';
  if (typeof value === 'boolean') return value ? 'Ja' : 'Nein';
  if (typeof value === 'object') return JSON.stringify(value);
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) return new Date(value).toLocaleString('de-DE');
  return String(value);
};

type Source = { key: string; label: string; fields: { key: string; label: string; wage?: boolean }[]; default_columns: string[] };
type Builder = {
  name: string;
  data_source: string;
  columns: string[];
  filters: Record<string, any>;
  sort: { field: string; direction: string }[];
  group_by: string[];
  aggregates: { field: string; op: string; alias?: string; label?: string }[];
  shared: boolean;
};

const emptyBuilder = (): Builder => ({
  name: '', data_source: 'shifts', columns: [], filters: { date_from: daysAgo(30), date_to: today() },
  sort: [], group_by: [], aggregates: [], shared: false,
});

export default function ReportingDock() {
  const [user, setUser] = useState<User>();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState('builder');
  const [catalog, setCatalog] = useState<any>();
  const [options, setOptions] = useState<any>({ workers: [], locations: [], positions: [], schedules: [] });
  const [definitions, setDefinitions] = useState<any[]>([]);
  const [schedules, setSchedules] = useState<any[]>([]);
  const [runs, setRuns] = useState<any[]>([]);
  const [builder, setBuilder] = useState<Builder>(emptyBuilder());
  const [preview, setPreview] = useState<any>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [scheduleForm, setScheduleForm] = useState<any>({ report: '', frequency: 'weekly', file_format: 'xlsx', recipients: '', local_hour: 8, weekday: 0, day_of_month: 1, timezone: 'Europe/Berlin' });

  const canView = !!user && (user.role === 'admin' || user.capabilities?.includes('reports.view'));
  const canManage = user?.role === 'admin' || !!catalog?.can_manage;
  const source: Source | undefined = catalog?.sources?.find((item: Source) => item.key === builder.data_source);
  const fields = source?.fields || [];

  useEffect(() => {
    if (!localStorage.getItem('access')) return;
    api<User>('auth/me/').then(setUser).catch(() => undefined);
  }, []);

  async function loadWorkspace() {
    setBusy(true);
    setError('');
    try {
      const [cat, opts, defs, sched, history] = await Promise.all([
        api('reports/builder/catalog/'), api('reports/builder/options/'), api('reports/builder/definitions/'),
        api('reports/builder/schedules/'), api('reports/builder/runs/'),
      ]);
      setCatalog(cat);
      setOptions(opts || {});
      setDefinitions(unpack(defs));
      setSchedules(unpack(sched));
      setRuns(unpack(history));
      setBuilder((current) => {
        const active: Source | undefined = cat?.sources?.find((item: Source) => item.key === current.data_source) || cat?.sources?.[0];
        return { ...current, data_source: active?.key || 'shifts', columns: current.columns.length ? current.columns : (active?.default_columns || []) };
      });
    } catch (reason: any) {
      setError(reason.message || 'Berichte konnten nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (open && canView) void loadWorkspace();
  }, [open]);

  function changeSource(key: string) {
    const next: Source | undefined = catalog?.sources?.find((item: Source) => item.key === key);
    setBuilder({ ...builder, data_source: key, columns: next?.default_columns || [], group_by: [], aggregates: [], sort: [] });
    setPreview(undefined);
  }

  function toggleColumn(key: string, checked: boolean) {
    const columns = checked ? [...new Set([...builder.columns, key])] : builder.columns.filter((item) => item !== key);
    setBuilder({ ...builder, columns });
  }

  function updateFilter(key: string, value: any) {
    setBuilder({ ...builder, filters: { ...builder.filters, [key]: value } });
  }

  async function previewReport() {
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await api('reports/builder/preview/', { method: 'POST', body: JSON.stringify(builder) });
      setPreview(result);
      setNotice(`${result.rows?.length || 0} Zeilen in der Vorschau.`);
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function saveReport() {
    if (!builder.name.trim()) { setError('Bitte einen Berichtsnamen eingeben.'); return; }
    setBusy(true); setError('');
    try {
      const row: any = await api('reports/builder/definitions/', { method: 'POST', body: JSON.stringify(builder) });
      setDefinitions((current) => [row, ...current.filter((item) => item.id !== row.id)]);
      setNotice('Bericht wurde gespeichert.');
      setTab('saved');
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  function editReport(row: any) {
    setBuilder({
      name: row.name, data_source: row.data_source, columns: row.columns || [], filters: row.filters || {},
      sort: row.sort || [], group_by: row.group_by || [], aggregates: row.aggregates || [], shared: !!row.shared,
    });
    setPreview(undefined);
    setTab('builder');
  }

  async function removeReport(id: string) {
    if (!window.confirm('Diesen gespeicherten Bericht löschen?')) return;
    setBusy(true);
    try {
      await api(`reports/builder/definitions/${id}/`, { method: 'DELETE' });
      setDefinitions((current) => current.filter((item) => item.id !== id));
      setNotice('Bericht wurde gelöscht.');
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function removeSchedule(id: string) {
    if (!window.confirm('Diesen Versandplan löschen?')) return;
    setBusy(true);
    try {
      await api(`reports/builder/schedules/${id}/`, { method: 'DELETE' });
      setSchedules((current) => current.filter((item) => item.id !== id));
      setNotice('Versandplan wurde gelöscht.');
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function createSchedule() {
    const recipients = String(scheduleForm.recipients || '').split(',').map((item) => item.trim()).filter(Boolean);
    if (!scheduleForm.report || !recipients.length) { setError('Bericht und Empfänger sind erforderlich.'); return; }
    setBusy(true); setError('');
    try {
      const row: any = await api('reports/builder/schedules/', {
        method: 'POST', body: JSON.stringify({ ...scheduleForm, recipients, local_hour: Number(scheduleForm.local_hour), weekday: Number(scheduleForm.weekday), day_of_month: Number(scheduleForm.day_of_month) }),
      });
      setSchedules((current) => [row, ...current]);
      setScheduleForm({ ...scheduleForm, recipients: '' });
      setNotice('Automatischer Versand wurde eingerichtet.');
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function downloadReport(row: any, fileFormat: 'csv' | 'xlsx') {
    setBusy(true); setError('');
    try {
      const access = localStorage.getItem('access') || '';
      const response = await fetch(`${API}/reports/builder/definitions/${row.id}/run/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...(access ? { Authorization: `Bearer ${access}` } : {}) },
        body: JSON.stringify({ file_format: fileFormat }),
      });
      if (!response.ok) {
        let detail = 'Export konnte nicht erstellt werden.';
        try { detail = (await response.json()).detail || detail; } catch { /* no-op */ }
        throw new Error(detail);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = `${row.name}.${fileFormat}`; anchor.click(); URL.revokeObjectURL(url);
      setNotice(`${fileFormat.toUpperCase()} wurde erstellt.`);
      const history: any = await api('reports/builder/runs/');
      setRuns(unpack(history));
    } catch (reason: any) { setError(reason.message); }
    finally { setBusy(false); }
  }

  const aggregateFields = useMemo(() => fields.filter((field) => /minutes|count|cost|rate|bedarf/i.test(field.key)), [fields]);

  if (!canView) return null;

  return (
    <>
      <button className="reporting-dock-button" onClick={() => setOpen(true)} aria-label="Berichte öffnen">
        <IonIcon icon={barChartOutline} /><span>Berichte</span>
      </button>
      <IonModal isOpen={open} onDidDismiss={() => setOpen(false)} cssClass="reporting-v8-modal">
        <div className="reporting-v8" data-testid="custom-reporting-panel">
          <header className="reporting-v8-head">
            <div><small>A+ WORKFORCE · ANALYTICS</small><h2>Report Builder</h2><p>Eigene Berichte, Labor-Analyse und automatischer Versand.</p></div>
            <div className="reporting-head-actions">
              <IonButton fill="outline" disabled={busy} onClick={loadWorkspace}><IonIcon slot="start" icon={refreshOutline} />Aktualisieren</IonButton>
              <IonButton fill="clear" onClick={() => setOpen(false)} aria-label="Berichte schließen"><IonIcon icon={closeOutline} /></IonButton>
            </div>
          </header>

          <IonSegment value={tab} onIonChange={(event) => setTab(String(eventValue(event)))} className="reporting-tabs">
            <IonSegmentButton value="builder">Builder</IonSegmentButton>
            <IonSegmentButton value="saved">Gespeichert <IonBadge>{definitions.length}</IonBadge></IonSegmentButton>
            {canManage && <IonSegmentButton value="schedules">Versand <IonBadge>{schedules.length}</IonBadge></IonSegmentButton>}
            <IonSegmentButton value="runs">Verlauf</IonSegmentButton>
          </IonSegment>

          {error && <div className="reporting-message error">{error}</div>}
          {notice && <div className="reporting-message success">{notice}</div>}
          {busy && <div className="reporting-busy"><IonSpinner name="dots" /> Berichtsdaten werden verarbeitet …</div>}

          {tab === 'builder' && catalog && (
            <main className="reporting-builder">
              <aside className="reporting-config">
                <section className="reporting-card">
                  <h3>1 · Datenquelle</h3>
                  <IonSelect label="Datenquelle" labelPlacement="stacked" fill="outline" value={builder.data_source} onIonChange={(event) => changeSource(String(eventValue(event)))}>
                    {catalog.sources?.map((item: Source) => <IonSelectOption key={item.key} value={item.key}>{item.label}</IonSelectOption>)}
                  </IonSelect>
                  <div className="reporting-filter-grid">
                    <IonInput type="date" label="Von" labelPlacement="stacked" fill="outline" value={builder.filters.date_from || ''} onIonInput={(event) => updateFilter('date_from', (event.target as HTMLIonInputElement).value || '')} />
                    <IonInput type="date" label="Bis" labelPlacement="stacked" fill="outline" value={builder.filters.date_to || ''} onIonInput={(event) => updateFilter('date_to', (event.target as HTMLIonInputElement).value || '')} />
                  </div>
                  <IonSelect label="Mitarbeiter" labelPlacement="stacked" fill="outline" placeholder="Alle im eigenen Bereich" value={builder.filters.worker || ''} onIonChange={(event) => updateFilter('worker', eventValue(event))}>
                    <IonSelectOption value="">Alle</IonSelectOption>{options.workers?.map((item: any) => <IonSelectOption key={item.id} value={item.id}>{item.number} · {item.name}</IonSelectOption>)}
                  </IonSelect>
                  <IonSelect label="Einsatzort" labelPlacement="stacked" fill="outline" placeholder="Alle" value={builder.filters.location || ''} onIonChange={(event) => updateFilter('location', eventValue(event))}>
                    <IonSelectOption value="">Alle</IonSelectOption>{options.locations?.map((item: any) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}
                  </IonSelect>
                  <IonSelect label="Position" labelPlacement="stacked" fill="outline" placeholder="Alle" value={builder.filters.position || ''} onIonChange={(event) => updateFilter('position', eventValue(event))}>
                    <IonSelectOption value="">Alle</IonSelectOption>{options.positions?.map((item: any) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}
                  </IonSelect>
                  <IonSelect label="Dienstplan" labelPlacement="stacked" fill="outline" placeholder="Alle" value={builder.filters.schedule || ''} onIonChange={(event) => updateFilter('schedule', eventValue(event))}>
                    <IonSelectOption value="">Alle</IonSelectOption>{options.schedules?.map((item: any) => <IonSelectOption key={item.id} value={item.id}>{item.name}</IonSelectOption>)}
                  </IonSelect>
                </section>

                <section className="reporting-card">
                  <h3>2 · Spalten</h3>
                  <div className="reporting-field-list">
                    {fields.map((field) => (
                      <label key={field.key} className="reporting-check">
                        <IonCheckbox checked={builder.columns.includes(field.key)} onIonChange={(event) => toggleColumn(field.key, !!event.detail.checked)} />
                        <span>{field.label}{field.wage && <small> Lohn</small>}</span>
                      </label>
                    ))}
                  </div>
                </section>

                <section className="reporting-card">
                  <h3>3 · Sortieren & gruppieren</h3>
                  <IonSelect label="Sortieren nach" labelPlacement="stacked" fill="outline" value={builder.sort[0]?.field || ''} onIonChange={(event) => setBuilder({ ...builder, sort: eventValue(event) ? [{ field: String(eventValue(event)), direction: builder.sort[0]?.direction || 'asc' }] : [] })}>
                    <IonSelectOption value="">Keine Sortierung</IonSelectOption>{fields.map((field) => <IonSelectOption key={field.key} value={field.key}>{field.label}</IonSelectOption>)}
                  </IonSelect>
                  {!!builder.sort.length && <IonSegment value={builder.sort[0].direction} onIonChange={(event) => setBuilder({ ...builder, sort: [{ ...builder.sort[0], direction: String(eventValue(event)) }] })}><IonSegmentButton value="asc">Aufsteigend</IonSegmentButton><IonSegmentButton value="desc">Absteigend</IonSegmentButton></IonSegment>}
                  <IonSelect label="Gruppieren nach" labelPlacement="stacked" fill="outline" value={builder.group_by[0] || ''} onIonChange={(event) => setBuilder({ ...builder, group_by: eventValue(event) ? [String(eventValue(event))] : [], aggregates: [] })}>
                    <IonSelectOption value="">Keine Gruppierung</IonSelectOption>{fields.map((field) => <IonSelectOption key={field.key} value={field.key}>{field.label}</IonSelectOption>)}
                  </IonSelect>
                  {!!builder.group_by.length && <div className="reporting-aggregate-row">
                    <IonSelect label="Kennzahl" labelPlacement="stacked" fill="outline" value={builder.aggregates[0]?.field || ''} onIonChange={(event) => setBuilder({ ...builder, aggregates: eventValue(event) ? [{ field: String(eventValue(event)), op: builder.aggregates[0]?.op || 'sum' }] : [] })}>
                      <IonSelectOption value="">Keine Kennzahl</IonSelectOption>{aggregateFields.map((field) => <IonSelectOption key={field.key} value={field.key}>{field.label}</IonSelectOption>)}
                    </IonSelect>
                    {!!builder.aggregates.length && <IonSelect label="Berechnung" labelPlacement="stacked" fill="outline" value={builder.aggregates[0].op} onIonChange={(event) => setBuilder({ ...builder, aggregates: [{ ...builder.aggregates[0], op: String(eventValue(event)) }] })}><IonSelectOption value="sum">Summe</IonSelectOption><IonSelectOption value="avg">Durchschnitt</IonSelectOption><IonSelectOption value="count">Anzahl</IonSelectOption><IonSelectOption value="min">Minimum</IonSelectOption><IonSelectOption value="max">Maximum</IonSelectOption></IonSelect>}
                  </div>}
                </section>
              </aside>

              <section className="reporting-preview">
                <div className="reporting-preview-head">
                  <div><h3>Vorschau</h3><p>Maximal 200 Zeilen in der Live-Vorschau. Exporte können bis zu 20.000 Zeilen enthalten.</p></div>
                  <IonButton disabled={busy || !builder.columns.length} onClick={previewReport}>Vorschau erstellen</IonButton>
                </div>
                {preview?.rows?.length ? (
                  <div className="reporting-table-wrap"><table><thead><tr>{preview.columns.map((column: any) => <th key={column.key}>{column.label}</th>)}</tr></thead><tbody>{preview.rows.map((row: any, index: number) => <tr key={index}>{preview.columns.map((column: any) => <td key={column.key}>{display(row[column.key])}</td>)}</tr>)}</tbody></table></div>
                ) : <div className="reporting-empty">Filter und Spalten wählen und anschließend die Vorschau starten.</div>}
                <div className="reporting-savebar">
                  <IonInput label="Berichtsname" labelPlacement="stacked" fill="outline" placeholder="z. B. Wochenstunden Frankfurt" value={builder.name} onIonInput={(event) => setBuilder({ ...builder, name: String((event.target as HTMLIonInputElement).value || '') })} />
                  {canManage && <label className="reporting-toggle"><span>Für andere Report-Nutzer teilen</span><IonToggle checked={builder.shared} onIonChange={(event) => setBuilder({ ...builder, shared: !!event.detail.checked })} /></label>}
                  <IonButton disabled={busy || !builder.columns.length} onClick={saveReport}><IonIcon slot="start" icon={saveOutline} />Bericht speichern</IonButton>
                </div>
              </section>
            </main>
          )}

          {tab === 'saved' && (
            <main className="reporting-list-page">
              <div className="reporting-section-title"><div><h3>Gespeicherte Berichte</h3><p>Jeder Lauf prüft die aktuellen Rollen und Scopes erneut.</p></div><IonButton fill="outline" onClick={() => { setBuilder(emptyBuilder()); setPreview(undefined); setTab('builder'); }}>Neuer Bericht</IonButton></div>
              <div className="reporting-list">
                {definitions.map((row) => <article key={row.id}>
                  <div><b>{row.name}</b><small>{catalog?.sources?.find((item: Source) => item.key === row.data_source)?.label || row.data_source} · {row.columns?.length || 0} Spalten{row.shared ? ' · geteilt' : ''}</small><span>Letzter Lauf: {row.last_run_at ? new Date(row.last_run_at).toLocaleString('de-DE') : 'noch nie'}</span></div>
                  <div className="reporting-row-actions"><IonButton size="small" fill="clear" onClick={() => editReport(row)}>Bearbeiten</IonButton><IonButton size="small" fill="outline" onClick={() => downloadReport(row, 'csv')}><IonIcon slot="start" icon={cloudDownloadOutline} />CSV</IonButton><IonButton size="small" onClick={() => downloadReport(row, 'xlsx')}>XLSX</IonButton>{(row.created_by === user?.id || canManage) && <IonButton size="small" color="danger" fill="clear" onClick={() => removeReport(row.id)}><IonIcon icon={trashOutline} /></IonButton>}</div>
                </article>)}
                {!definitions.length && <div className="reporting-empty">Noch keine gespeicherten Berichte.</div>}
              </div>
            </main>
          )}

          {tab === 'schedules' && canManage && (
            <main className="reporting-list-page reporting-schedules">
              <section className="reporting-card schedule-form">
                <h3>Automatischen Versand einrichten</h3>
                <div className="reporting-schedule-grid">
                  <IonSelect label="Bericht" labelPlacement="stacked" fill="outline" value={scheduleForm.report} onIonChange={(event) => setScheduleForm({ ...scheduleForm, report: eventValue(event) })}>{definitions.map((row) => <IonSelectOption value={row.id} key={row.id}>{row.name}</IonSelectOption>)}</IonSelect>
                  <IonSelect label="Frequenz" labelPlacement="stacked" fill="outline" value={scheduleForm.frequency} onIonChange={(event) => setScheduleForm({ ...scheduleForm, frequency: eventValue(event) })}>{catalog?.frequencies?.map((item: any) => <IonSelectOption value={item.key} key={item.key}>{item.label}</IonSelectOption>)}</IonSelect>
                  <IonSelect label="Format" labelPlacement="stacked" fill="outline" value={scheduleForm.file_format} onIonChange={(event) => setScheduleForm({ ...scheduleForm, file_format: eventValue(event) })}>{catalog?.formats?.map((item: any) => <IonSelectOption value={item.key} key={item.key}>{item.label}</IonSelectOption>)}</IonSelect>
                  <IonInput type="number" min="0" max="23" label="Stunde" labelPlacement="stacked" fill="outline" value={scheduleForm.local_hour} onIonInput={(event) => setScheduleForm({ ...scheduleForm, local_hour: (event.target as HTMLIonInputElement).value })} />
                  {scheduleForm.frequency === 'weekly' && <IonSelect label="Wochentag" labelPlacement="stacked" fill="outline" value={scheduleForm.weekday} onIonChange={(event) => setScheduleForm({ ...scheduleForm, weekday: eventValue(event) })}>{['Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag','Sonntag'].map((label, index) => <IonSelectOption value={index} key={label}>{label}</IonSelectOption>)}</IonSelect>}
                  {scheduleForm.frequency === 'monthly' && <IonInput type="number" min="1" max="28" label="Tag im Monat" labelPlacement="stacked" fill="outline" value={scheduleForm.day_of_month} onIonInput={(event) => setScheduleForm({ ...scheduleForm, day_of_month: (event.target as HTMLIonInputElement).value })} />}
                  <IonInput className="reporting-recipient" label="Empfänger" labelPlacement="stacked" fill="outline" placeholder="ops@firma.de, chef@firma.de" value={scheduleForm.recipients} onIonInput={(event) => setScheduleForm({ ...scheduleForm, recipients: (event.target as HTMLIonInputElement).value || '' })} />
                  <IonButton onClick={createSchedule} disabled={busy}><IonIcon slot="start" icon={timeOutline} />Versand speichern</IonButton>
                </div>
              </section>
              <div className="reporting-list">{schedules.map((row) => <article key={row.id}><div><b>{row.report_name}</b><small>{row.frequency} · {row.file_format.toUpperCase()} · {row.recipients?.join(', ')}</small><span>Nächster Lauf: {new Date(row.next_run_at).toLocaleString('de-DE')}</span></div><IonButton size="small" fill="clear" color="danger" onClick={() => removeSchedule(row.id)}><IonIcon icon={trashOutline} /></IonButton></article>)}{!schedules.length && <div className="reporting-empty">Noch kein automatischer Versand eingerichtet.</div>}</div>
            </main>
          )}

          {tab === 'runs' && (
            <main className="reporting-list-page">
              <div className="reporting-section-title"><div><h3>Ausführungsverlauf</h3><p>Manuelle und geplante Exporte inklusive Checksumme.</p></div></div>
              <div className="reporting-list">{runs.map((row) => <article key={row.id}><div><b>{row.report_name || 'Bericht'}</b><small>{row.trigger} · {row.file_format?.toUpperCase()} · {row.row_count} Zeilen</small><span>{new Date(row.created_at).toLocaleString('de-DE')} · {row.status}{row.checksum ? ` · ${row.checksum.slice(0, 12)}…` : ''}</span>{row.error && <em>{row.error}</em>}</div><IonBadge color={row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'}>{row.status}</IonBadge></article>)}{!runs.length && <div className="reporting-empty">Noch keine Berichtsläufe vorhanden.</div>}</div>
            </main>
          )}
        </div>
      </IonModal>
    </>
  );
}

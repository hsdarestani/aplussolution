import React, { useEffect, useMemo, useRef, useState } from 'react';
import { IonAlert, IonBadge, IonButton, IonContent, IonIcon, IonModal, IonSpinner, IonToast } from '@ionic/react';
import {
  alertCircleOutline,
  checkmarkCircleOutline,
  cloudUploadOutline,
  documentTextOutline,
  notificationsOutline,
  refreshOutline,
  sendOutline,
  shieldCheckmarkOutline,
} from 'ionicons/icons';
import { api } from './api';
import './document-center-v5.css';

type TemplateState = {
  id: string;
  slug: string;
  name: string;
  version: string;
  source_format: string;
  source_installed: boolean;
  source_checksum: string;
  expected_source_name?: string;
  requires_signature: boolean;
  signature_roles: string[];
  required_field_count: number;
  ready: boolean;
  issues: { code: string; label: string }[];
};

type ActionItem = {
  type: 'template' | 'contract';
  severity: 'critical' | 'warning' | 'info';
  action: string;
  id: string;
  slug?: string;
  title: string;
  message: string;
};

type MissingField = {
  field: string;
  label: string;
  source?: string;
};

type FixTarget = {
  state: any;
  contract: any;
  fields: MissingField[];
  definitions: Record<string, any>;
  values: Record<string, any>;
};

const roleLabel: Record<string, string> = {
  employee: 'Mitarbeiter',
  employer: 'Arbeitgeber',
  client: 'Kunde',
};

const actionLabel: Record<string, string> = {
  install_source: 'Originaldatei installieren',
  fix_data: 'Daten prüfen',
  generate: 'PDF erstellen',
  send: 'Versenden',
  signature: 'Signatur offen',
  deadline: 'Frist prüfen',
};

function sourceLabel(source?: string) {
  if (source?.startsWith('master.')) return 'Personalstammdaten';
  if (source?.startsWith('worker.') || source?.startsWith('user.')) return 'Mitarbeiterprofil';
  if (source?.startsWith('company.')) return 'Firmendaten';
  if (source?.startsWith('contract.')) return 'Vertrag';
  return 'Vertrag';
}

function normalizeFieldValue(definition: any, raw: any) {
  const kind = definition?.type || 'text';
  if (kind === 'boolean') return raw === true || raw === 'true';
  if (kind === 'number' || kind === 'money') return raw === '' || raw == null ? '' : Number(raw);
  return raw;
}

export default function DocumentCenterV5({ onChanged }: { onChanged?: () => void | Promise<void> }) {
  const [data, setData] = useState<any>();
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [pendingSource, setPendingSource] = useState<{ template: TemplateState; file: File }>();
  const [fixTarget, setFixTarget] = useState<FixTarget>();
  const [fixBusy, setFixBusy] = useState(false);
  const fileInputs = useRef<Record<string, HTMLInputElement | null>>({});

  const load = async () => {
    setBusy(true);
    try {
      setData(await api('document-center/'));
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const summary = data?.summary || {};
  const actions: ActionItem[] = data?.actions || [];
  const templates: TemplateState[] = data?.templates || [];
  const visibleActions = expanded ? actions : actions.slice(0, 8);

  async function openMissingFields(item: ActionItem) {
    const state = (data?.contracts || []).find((contract: any) => contract.id === item.id);
    const fields: MissingField[] = state?.missing_fields || [];
    if (!fields.length) {
      sessionStorage.setItem('aplus:focus', JSON.stringify({ view: 'contracts', id: item.id, source: 'document-center' }));
      window.setTimeout(() => document.getElementById(`contract-${item.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 40);
      setToast('Keine fehlenden Pflichtangaben gefunden. Vertrag wurde geöffnet.');
      return;
    }

    setFixBusy(true);
    try {
      const [contract, catalog]: any[] = await Promise.all([
        api(`contracts/${item.id}/`),
        api('document-catalog/'),
      ]);
      const template = (catalog?.documents || []).find((entry: any) => entry.slug === contract.template_slug);
      const definitions = Object.fromEntries((template?.fields || []).map((field: any) => [field.name, field]));
      let master: any = undefined;
      if (contract.worker) {
        try {
          master = await api(`workers/${contract.worker}/master-data/`);
        } catch {
          master = undefined;
        }
      }
      const values: Record<string, any> = {};
      for (const field of fields) {
        const sourceKey = field.source?.startsWith('master.') ? field.source.slice('master.'.length) : '';
        values[field.field] = contract.variables?.[field.field] ?? (sourceKey ? master?.data?.[sourceKey] : '') ?? '';
      }
      setFixTarget({ state, contract, fields, definitions, values });
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setFixBusy(false);
    }
  }

  async function saveMissingFields() {
    if (!fixTarget) return;
    const missing = fixTarget.fields.filter((field) => {
      const value = fixTarget.values[field.field];
      return value == null || String(value).trim() === '';
    });
    if (missing.length) {
      setToast(`Bitte noch ausfüllen: ${missing.map((field) => field.label).join(', ')}`);
      return;
    }

    setFixBusy(true);
    try {
      const masterPatch: Record<string, any> = {};
      const variablePatch: Record<string, any> = { ...(fixTarget.contract.variables || {}) };
      for (const field of fixTarget.fields) {
        const definition = fixTarget.definitions[field.field] || {};
        const normalized = normalizeFieldValue(definition, fixTarget.values[field.field]);
        if (field.source?.startsWith('master.') && fixTarget.contract.worker) {
          masterPatch[field.source.slice('master.'.length)] = normalized;
        } else {
          variablePatch[field.field] = normalized;
        }
      }

      if (fixTarget.contract.worker && Object.keys(masterPatch).length) {
        await api(`workers/${fixTarget.contract.worker}/master-data/`, {
          method: 'PATCH',
          body: JSON.stringify({ data: masterPatch }),
        });
      }
      if (Object.keys(variablePatch).length !== Object.keys(fixTarget.contract.variables || {}).length || fixTarget.fields.some((field) => !field.source?.startsWith('master.'))) {
        await api(`contracts/${fixTarget.contract.id}/`, {
          method: 'PATCH',
          body: JSON.stringify({ variables: variablePatch }),
        });
      }

      setFixTarget(undefined);
      await load();
      await onChanged?.();
      setToast('Pflichtangaben gespeichert. Der Vertrag wurde erneut geprüft.');
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setFixBusy(false);
    }
  }

  async function contractAction(item: ActionItem) {
    if (item.type !== 'contract') return;
    if (item.action === 'fix_data') {
      await openMissingFields(item);
      return;
    }
    try {
      if (item.action === 'generate') {
        await api(`contracts/${item.id}/generate_pdf/`, { method: 'POST', body: '{}' });
        setToast('Dokument wurde erzeugt.');
      } else if (item.action === 'send') {
        await api(`contracts/${item.id}/send/`, { method: 'POST', body: '{}' });
        setToast('Dokument wurde versendet.');
      } else {
        sessionStorage.setItem('aplus:focus', JSON.stringify({ view: 'contracts', id: item.id, source: 'document-center' }));
        window.setTimeout(() => document.getElementById(`contract-${item.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 40);
        setToast('Der Vorgang wurde in der Vertragsliste geöffnet.');
      }
      await load();
      await onChanged?.();
    } catch (error: any) {
      setToast(error.message);
    }
  }

  function clearPendingSource() {
    const slug = pendingSource?.template.slug;
    if (slug) {
      const input = fileInputs.current[slug];
      if (input) input.value = '';
    }
    setPendingSource(undefined);
  }

  function selectSource(template: TemplateState, file?: File) {
    if (!file) return;
    setPendingSource({ template, file });
  }

  async function installSource(template: TemplateState, file: File, version: string) {
    const form = new FormData();
    form.append('file', file);
    if (version) form.append('version', version);
    setBusy(true);
    try {
      await api(`document-center/templates/${template.slug}/source/`, { method: 'POST', body: form });
      setToast(`${template.name}: Originaldatei wurde installiert.`);
      await load();
      await onChanged?.();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      const input = fileInputs.current[template.slug];
      if (input) input.value = '';
      setPendingSource(undefined);
      setBusy(false);
    }
  }

  async function runReminders() {
    setBusy(true);
    try {
      const result: any = await api('document-center/reminders/run/', { method: 'POST', body: '{}' });
      setToast(`${result.notifications || 0} Benachrichtigung(en), ${result.emails || 0} E-Mail(s) neu ausgelöst.`);
      await load();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  const readyPercent = useMemo(() => summary.templates_total ? Math.round((summary.templates_ready || 0) * 100 / summary.templates_total) : 0, [summary]);

  if (!data && busy) return <div className="doc-center-loading"><IonSpinner /><span>Dokumentstatus wird geprüft …</span></div>;
  if (!data) return null;

  return (
    <section className="document-center-v5" data-testid="document-center-v5">
      <div className="doc-center-hero">
        <div>
          <small>DOKUMENTE · READINESS</small>
          <h2>Vor Erzeugen, Versand und Signatur wissen, was fehlt.</h2>
          <p>Die Originaltexte kommen ausschließlich aus den installierten Firmenvorlagen. Das System prüft Daten, Version, Quelldatei, PDF-Stand, Signaturen und Fristen.</p>
        </div>
        <div className="doc-center-hero-actions">
          <IonButton fill="outline" disabled={busy} onClick={() => void load()}><IonIcon slot="start" icon={refreshOutline} />Prüfen</IonButton>
          <IonButton fill="outline" disabled={busy} onClick={runReminders}><IonIcon slot="start" icon={notificationsOutline} />Reminder prüfen</IonButton>
        </div>
      </div>

      <div className="doc-center-stats">
        <DocStat label="Vorlagen bereit" value={`${summary.templates_ready || 0}/${summary.templates_total || 0}`} note={`${readyPercent}%`} good={summary.templates_ready === summary.templates_total} />
        <DocStat label="Originaldatei fehlt" value={summary.templates_missing_source || 0} danger={summary.templates_missing_source > 0} />
        <DocStat label="Verträge blockiert" value={summary.blocked || 0} danger={summary.blocked > 0} />
        <DocStat label="PDF ausstehend" value={summary.ready_to_generate || 0} />
        <DocStat label="Signaturen offen" value={summary.awaiting_signature || 0} />
      </div>

      <div className="doc-center-grid">
        <div className="doc-center-panel doc-actions-panel">
          <div className="doc-panel-head"><div><small>HANDLUNGSBEDARF</small><h3>Was als Nächstes passieren muss</h3></div><IonBadge>{actions.length}</IonBadge></div>
          {visibleActions.map((item, index) => (
            <div className={`doc-action severity-${item.severity}`} key={`${item.type}-${item.id}-${item.action}-${index}`}>
              <span className="doc-action-icon"><IonIcon icon={item.action === 'send' ? sendOutline : item.action === 'signature' ? shieldCheckmarkOutline : item.action === 'install_source' ? cloudUploadOutline : alertCircleOutline} /></span>
              <div className="doc-action-copy"><small>{actionLabel[item.action] || item.action}</small><b>{item.title}</b><span>{item.message}</span></div>
              {item.action === 'install_source' && item.slug ? (
                <IonButton size="small" fill="outline" onClick={() => fileInputs.current[item.slug!]?.click()}>Datei wählen</IonButton>
              ) : (
                <IonButton size="small" disabled={fixBusy} fill={item.severity === 'critical' ? 'solid' : 'outline'} onClick={() => void contractAction(item)}>{item.action === 'fix_data' ? 'Fehlende Daten' : 'Öffnen'}</IonButton>
              )}
            </div>
          ))}
          {!actions.length && <div className="doc-center-empty"><IonIcon icon={checkmarkCircleOutline} /><b>Kein Dokument-Handlungsbedarf.</b></div>}
          {actions.length > 8 && <button type="button" className="doc-more" onClick={() => setExpanded(!expanded)}>{expanded ? 'Weniger anzeigen' : `Alle ${actions.length} Vorgänge anzeigen`}</button>}
        </div>

        <div className="doc-center-panel templates-panel">
          <div className="doc-panel-head"><div><small>8 ORIGINALVORLAGEN</small><h3>Installationsstatus</h3></div></div>
          <div className="template-readiness-list">
            {templates.map((template) => (
              <div className="template-readiness" key={template.id}>
                <span className={`template-state ${template.ready ? 'ready' : 'missing'}`}><IonIcon icon={template.ready ? checkmarkCircleOutline : documentTextOutline} /></span>
                <div className="template-copy">
                  <b>{template.name}</b>
                  <small>v{template.version} · {template.source_format.toUpperCase()} · {template.required_field_count} Pflichtfeld(er)</small>
                  <span>{template.source_installed ? `Original installiert · ${template.source_checksum.slice(0, 10)}…` : `Erwartet: ${template.expected_source_name || 'Originaldatei'}`}</span>
                  {!!template.signature_roles.length && <em>Signatur: {template.signature_roles.map((role) => roleLabel[role] || role).join(' + ')}</em>}
                </div>
                <input
                  ref={(node) => { fileInputs.current[template.slug] = node; }}
                  type="file"
                  hidden
                  accept={template.source_format === 'docx' ? '.docx' : '.pdf'}
                  onChange={(event) => selectSource(template, event.target.files?.[0])}
                />
                <IonButton size="small" fill="clear" disabled={busy} onClick={() => fileInputs.current[template.slug]?.click()}>{template.source_installed ? 'Ersetzen' : 'Installieren'}</IonButton>
              </div>
            ))}
          </div>
        </div>
      </div>

      <IonModal isOpen={!!fixTarget} onDidDismiss={() => !fixBusy && setFixTarget(undefined)}>
        <IonContent className="ion-padding">
          <div style={{ maxWidth: 760, margin: '0 auto', padding: '8px 0 28px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, marginBottom: 18 }}>
              <div>
                <small style={{ fontWeight: 800, letterSpacing: '.12em', opacity: .55 }}>VERTRAG · PFLICHTANGABEN</small>
                <h2 style={{ margin: '6px 0 6px' }}>Fehlende Daten ergänzen</h2>
                <p style={{ margin: 0, opacity: .68 }}>{fixTarget?.contract?.title} · {fixTarget?.state?.subject}</p>
              </div>
              <IonButton fill="clear" disabled={fixBusy} onClick={() => setFixTarget(undefined)}>Schließen</IonButton>
            </div>
            <div style={{ border: '1px solid rgba(220,38,38,.18)', background: 'rgba(220,38,38,.035)', borderRadius: 16, padding: 14, marginBottom: 16 }}>
              <b>{fixTarget?.fields.length || 0} Pflichtangabe(n) fehlen.</b>
              <div style={{ marginTop: 5, fontSize: 13, opacity: .68 }}>Personalstammdaten werden dauerhaft beim Mitarbeiter gespeichert; vertragsbezogene Werte nur in diesem Vertrag.</div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: 12 }}>
              {fixTarget?.fields.map((field) => {
                const definition = fixTarget.definitions[field.field] || {};
                const kind = definition.type || 'text';
                const value = fixTarget.values[field.field] ?? '';
                return <label key={field.field} style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 12, border: '1px solid var(--line,#e5e7eb)', borderRadius: 14, background: 'var(--card,#fff)' }}>
                  <span style={{ fontWeight: 700, fontSize: 14 }}>{field.label} *</span>
                  <small style={{ opacity: .55 }}>{sourceLabel(field.source)}</small>
                  {kind === 'choice' ? (
                    <select value={String(value)} onChange={(event) => setFixTarget((current) => current ? ({ ...current, values: { ...current.values, [field.field]: event.target.value } }) : current)} style={{ minHeight: 42, border: '1px solid #d0d5dd', borderRadius: 10, padding: '0 10px', background: 'transparent', color: 'inherit' }}>
                      <option value="">Bitte wählen</option>
                      {(definition.choices || []).map((choice: string) => <option value={choice} key={choice}>{choice}</option>)}
                    </select>
                  ) : kind === 'boolean' ? (
                    <select value={value === true || value === 'true' ? 'true' : value === false || value === 'false' ? 'false' : ''} onChange={(event) => setFixTarget((current) => current ? ({ ...current, values: { ...current.values, [field.field]: event.target.value } }) : current)} style={{ minHeight: 42, border: '1px solid #d0d5dd', borderRadius: 10, padding: '0 10px', background: 'transparent', color: 'inherit' }}>
                      <option value="">Bitte wählen</option>
                      <option value="true">Ja</option>
                      <option value="false">Nein</option>
                    </select>
                  ) : (
                    <input
                      type={kind === 'date' ? 'date' : kind === 'number' || kind === 'money' ? 'number' : 'text'}
                      step={kind === 'money' ? '0.01' : undefined}
                      value={String(value)}
                      onChange={(event) => setFixTarget((current) => current ? ({ ...current, values: { ...current.values, [field.field]: event.target.value } }) : current)}
                      style={{ minHeight: 42, border: '1px solid #d0d5dd', borderRadius: 10, padding: '0 11px', background: 'transparent', color: 'inherit', font: 'inherit' }}
                    />
                  )}
                </label>;
              })}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
              <IonButton fill="outline" disabled={fixBusy} onClick={() => setFixTarget(undefined)}>Abbrechen</IonButton>
              <IonButton disabled={fixBusy} onClick={() => void saveMissingFields()}>{fixBusy ? <IonSpinner name="dots" /> : 'Speichern & erneut prüfen'}</IonButton>
            </div>
          </div>
        </IonContent>
      </IonModal>

      <IonAlert
        isOpen={!!pendingSource}
        onDidDismiss={clearPendingSource}
        header="Originalvorlage installieren"
        message={pendingSource ? `${pendingSource.template.name} · ${pendingSource.file.name}` : ''}
        inputs={[{
          name: 'version',
          type: 'text',
          placeholder: 'Version',
          value: pendingSource?.template.version || '',
        }]}
        buttons={[
          { text: 'Abbrechen', role: 'cancel' },
          {
            text: pendingSource?.template.source_installed ? 'Ersetzen' : 'Installieren',
            handler: (values) => {
              if (!pendingSource) return false;
              const version = String(values?.version ?? pendingSource.template.version ?? '').trim();
              void installSource(pendingSource.template, pendingSource.file, version);
              return true;
            },
          },
        ]}
      />
      <IonToast isOpen={!!toast} message={toast} duration={4200} onDidDismiss={() => setToast('')} />
    </section>
  );
}

function DocStat({ label, value, note, danger, good }: { label: string; value: any; note?: string; danger?: boolean; good?: boolean }) {
  return <div className={`doc-stat ${danger ? 'danger' : ''} ${good ? 'good' : ''}`}><small>{label}</small><strong>{value}</strong>{note && <span>{note}</span>}</div>;
}

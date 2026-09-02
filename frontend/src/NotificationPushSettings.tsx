import React, { useEffect, useMemo, useState } from 'react';
import { IonButton, IonSpinner, IonToggle } from '@ionic/react';
import { api } from './api';

type PushRule = {
  key: string;
  label: string;
  enabled: boolean;
  title_template: string;
  body_template: string;
  display_title: string;
  display_body: string;
  preview_source: 'latest' | 'example';
};

export default function NotificationPushSettings({ role }: { role?: string }) {
  const allowed = role === 'admin' || role === 'manager';
  const [rules, setRules] = useState<PushRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const dirty = useMemo(() => rules.length > 0, [rules]);

  useEffect(() => {
    if (!allowed) return;
    let mounted = true;
    setLoading(true);
    api('push/settings/')
      .then((response: any) => {
        if (mounted) setRules(Array.isArray(response?.rules) ? response.rules : []);
      })
      .catch((error: any) => mounted && setMessage(error?.message || 'Benachrichtigungseinstellungen konnten nicht geladen werden.'))
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, [allowed]);

  if (!allowed) return null;

  function update(key: string, patch: Partial<PushRule>) {
    setRules(current => current.map(rule => rule.key === key ? { ...rule, ...patch } : rule));
  }

  async function save() {
    setSaving(true);
    setMessage('');
    try {
      const response: any = await api('push/settings/', {
        method: 'PUT',
        body: JSON.stringify({ rules }),
      });
      setRules(Array.isArray(response?.rules) ? response.rules : rules);
      setMessage('Benachrichtigungseinstellungen gespeichert.');
    } catch (error: any) {
      setMessage(error?.message || 'Speichern fehlgeschlagen.');
    } finally {
      setSaving(false);
    }
  }

  return <section className="panel push-settings-panel">
    <div className="section-head">
      <div>
        <h3>Push-Benachrichtigungen</h3>
        <p>Aktuelle Texte ansehen, bearbeiten und speichern. Unveränderte Texte bleiben dynamisch. Ein bearbeiteter Text wird als eigener Text für diesen Ereignistyp gespeichert.</p>
      </div>
      <IonButton size="small" disabled={saving || loading || !dirty} onClick={() => void save()}>
        {saving ? <IonSpinner name="crescent" /> : 'Speichern'}
      </IonButton>
    </div>
    {loading && <div className="empty">Benachrichtigungseinstellungen werden geladen…</div>}
    {!loading && <div className="push-rule-grid">
      {rules.map(rule => <article className="push-rule" key={rule.key}>
        <div className="push-rule-head">
          <div><b>{rule.label}</b><small>{rule.key}</small></div>
          <IonToggle checked={rule.enabled} onIonChange={event => update(rule.key, { enabled: event.detail.checked })} aria-label={`${rule.label} aktivieren`} />
        </div>
        <small>{rule.preview_source === 'latest' ? 'Aktueller Text · letzte Benachrichtigung' : 'Textbeispiel · noch keine Benachrichtigung'}</small>
        <label>
          <span>Titel</span>
          <input value={rule.display_title ?? rule.title_template} onChange={event => update(rule.key, { title_template: event.target.value, display_title: event.target.value })} maxLength={240} />
        </label>
        <label>
          <span>Text</span>
          <textarea value={rule.display_body ?? rule.body_template} onChange={event => update(rule.key, { body_template: event.target.value, display_body: event.target.value })} rows={2} maxLength={4000} />
        </label>
      </article>)}
    </div>}
    {!!message && <p className="push-settings-message">{message}</p>}
    <style>{`
      .push-settings-panel{margin:18px 0}.push-rule-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px}.push-rule{border:1px solid #e4e7ec;border-radius:16px;padding:14px;background:#fff}.push-rule-head{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:10px}.push-rule-head b{display:block;color:#101828}.push-rule-head small{display:block;margin-top:2px;color:#98a2b3;font-size:11px}.push-rule label{display:block;margin-top:8px}.push-rule label>span{display:block;font-size:12px;font-weight:700;color:#475467;margin-bottom:4px}.push-rule input,.push-rule textarea{width:100%;box-sizing:border-box;border:1px solid #d0d5dd;border-radius:10px;padding:9px 10px;background:#fff;color:#101828;font:inherit;font-size:13px;outline:none}.push-rule textarea{resize:vertical;min-height:58px}.push-rule input:focus,.push-rule textarea:focus{border-color:#2e90fa;box-shadow:0 0 0 3px rgba(46,144,250,.12)}.push-settings-message{margin:10px 2px 0;color:#344054;font-size:13px}@media(max-width:700px){.push-rule-grid{grid-template-columns:1fr}.push-settings-panel .section-head{align-items:flex-start}.push-settings-panel .section-head p{max-width:100%}}
    `}</style>
  </section>;
}

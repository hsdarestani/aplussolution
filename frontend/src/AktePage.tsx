import React, { useEffect, useMemo, useState } from 'react';
import { IonBadge, IonButton, IonIcon, IonInput, IonSelect, IonSelectOption, IonTextarea, IonToggle } from '@ionic/react';
import { briefcaseOutline, calendarOutline, documentTextOutline, folderOpenOutline, peopleOutline, receiptOutline } from 'ionicons/icons';
import { api, User } from './api';
import { BUSINESS_TIME_ZONE } from './berlinLocale';
import './akte-page.css';

type AkteKind = 'worker' | 'client';
type AkteData = {
  kind: AkteKind;
  title: string;
  number?: string;
  profile?: any;
  master_data?: any;
  summary?: Record<string, number>;
  contracts?: any[];
  document_folders?: Array<{ key: string; label: string; count: number; items: any[] }>;
  payroll?: any[];
  shifts?: any[];
  orders?: any[];
  locations?: any[];
};

const statusLabel: Record<string, string> = {
  draft: 'Entwurf', ready: 'Prüfbereit', sent: 'Versendet', signed: 'Unterzeichnet', expired: 'Abgelaufen', cancelled: 'Storniert',
  published: 'Veröffentlicht', confirmed: 'Bestätigt', completed: 'Abgeschlossen', new: 'Neu', planning: 'In Planung', done: 'Abgeschlossen',
};

function formatDate(value?: string, withTime = true) {
  if (!value) return '–';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('de-DE', {
    timeZone: BUSINESS_TIME_ZONE,
    day: '2-digit', month: '2-digit', year: 'numeric',
    ...(withTime && value.includes('T') ? { hour: '2-digit', minute: '2-digit' } : {}),
  }).format(date);
}

function fileLink(href?: string, label = 'Öffnen') {
  return href ? <a className="akte-link" href={href} target="_blank" rel="noreferrer">{label}</a> : <span className="akte-muted">Keine Datei</span>;
}

const text = (value: any) => value == null || value === '' ? '–' : String(value);
const manager = (user: User) => user.role === 'admin' || user.role === 'manager';

export default function AktePage({ user }: { user: User }) {
  const params = new URLSearchParams(window.location.search);
  const kind = (params.get('akte_kind') === 'client' ? 'client' : 'worker') as AkteKind;
  const id = params.get('akte_id') || '';
  const [data, setData] = useState<AkteData>();
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [profile, setProfile] = useState<any>({});
  const [master, setMaster] = useState<any>({});

  const load = async () => {
    if (!id) { setMessage('Keine Akte ausgewählt.'); setLoading(false); return; }
    setLoading(true);
    setMessage('');
    try {
      const endpoint = kind === 'worker' ? `workers/${id}/akte/` : `clients/${id}/akte/`;
      const result = await api<AkteData>(endpoint);
      setData(result);
      if (kind === 'worker') {
        setProfile({
          first_name: result.profile?.user_detail?.first_name || '', last_name: result.profile?.user_detail?.last_name || '',
          email: result.profile?.user_detail?.email || '', phone: result.profile?.user_detail?.phone || '', employee_number: result.profile?.employee_number || '',
          employment_type: result.profile?.employment_type || 'minijob', monthly_hours: result.profile?.monthly_hours || '', tariff_hourly_rate: result.profile?.tariff_hourly_rate || '',
          extra_allowance: result.profile?.extra_allowance || 0, ranking_points: result.profile?.ranking_points || 0, active: result.profile?.active !== false,
        });
        setMaster(result.master_data?.data || {});
      } else {
        const contact = result.profile?.contacts_detail?.[0] || {};
        setProfile({
          name: result.profile?.name || '', customer_number: result.profile?.customer_number || '', address: result.profile?.address || '', vat_id: result.profile?.vat_id || '',
          notes: result.profile?.notes || '', active: result.profile?.active !== false, contract_visibility_enabled: result.profile?.contract_visibility_enabled !== false,
          contact_first_name: contact.first_name || '', contact_last_name: contact.last_name || '', contact_email: contact.email || '', contact_phone: contact.phone || '',
        });
      }
    } catch (error: any) { setMessage(error?.message || 'Akte konnte nicht geladen werden.'); }
    finally { setLoading(false); }
  };

  useEffect(() => { void load(); }, [id, kind]);

  async function save() {
    if (!manager(user) || !id) return;
    setSaving(true); setMessage('');
    try {
      const endpoint = kind === 'worker' ? `workers/${id}/akte/` : `clients/${id}/akte/`;
      const payload = kind === 'worker' ? { profile, master_data: master } : { profile };
      const result = await api<AkteData>(endpoint, { method: 'PATCH', body: JSON.stringify(payload) });
      setData(result); setEditing(false); setMessage('Akte wurde gespeichert.'); await load();
    } catch (error: any) { setMessage(error?.message || 'Akte konnte nicht gespeichert werden.'); }
    finally { setSaving(false); }
  }

  const summary = useMemo(() => Object.entries(data?.summary || {}), [data]);
  const back = () => {
    const url = new URL(window.location.href); url.searchParams.set('view', 'people'); url.searchParams.set('people_kind', kind === 'client' ? 'clients' : 'workers'); url.searchParams.delete('akte_kind'); url.searchParams.delete('akte_id');
    window.history.pushState({ view: 'people' }, '', `${url.pathname}${url.search}`); window.dispatchEvent(new PopStateEvent('popstate'));
  };

  if (loading) return <div className="akte-page"><div className="akte-loading">Digitale Akte wird geladen …</div></div>;
  if (!data) return <div className="akte-page"><button className="akte-back" onClick={back}>← Zurück</button><div className="akte-message">{message || 'Akte nicht gefunden.'}</div></div>;

  return <div className="akte-page" data-testid="akte-page">
    <div className="akte-toolbar"><button className="akte-back" onClick={back}>← Personal & Kunden</button><div className="akte-actions">{manager(user) && (editing ? <><IonButton fill="outline" onClick={() => { setEditing(false); void load(); }}>Abbrechen</IonButton><IonButton disabled={saving} onClick={() => void save()}>{saving ? 'Speichert …' : 'Änderungen speichern'}</IonButton></> : <IonButton onClick={() => setEditing(true)}>Profil bearbeiten</IonButton>)}</div></div>
    <header className="akte-hero">
      <div className={`akte-avatar ${data.kind}`}><IonIcon icon={data.kind === 'worker' ? peopleOutline : briefcaseOutline} /></div>
      <div className="akte-hero-copy"><small>DIGITALE AKTE · {data.kind === 'worker' ? 'MITARBEITER' : 'KUNDE'}</small><h1>{data.title}</h1><p>{data.number || 'Ohne Nummer'}{data.kind === 'worker' && data.profile?.user_detail?.email ? ` · ${data.profile.user_detail.email}` : ''}</p></div>
      <IonBadge color={data.profile?.active === false ? 'medium' : 'success'}>{data.profile?.active === false ? 'Inaktiv' : 'Aktiv'}</IonBadge>
    </header>

    {message && <div className="akte-message" role="status">{message}</div>}

    <div className="akte-summary">{summary.map(([key, value]) => <div key={key}><strong>{value}</strong><span>{({contracts:'Verträge',documents:'Dokumente',payroll:'Lohnabrechnungen',shifts:'Einsätze',orders:'Aufträge',locations:'Einsatzorte'} as any)[key] || key}</span></div>)}</div>

    <section className="akte-section">
      <div className="akte-section-head"><div><h2>Stammdaten</h2><p>Kontaktdaten, Beschäftigung und abrechnungsrelevante Informationen.</p></div></div>
      {editing && manager(user) ? (
        data.kind === 'worker' ? <>
          <div className="akte-form-grid">
            <IonInput fill="outline" label="Vorname" labelPlacement="floating" value={profile.first_name} onIonInput={e=>setProfile({...profile,first_name:e.detail.value})}/>
            <IonInput fill="outline" label="Nachname" labelPlacement="floating" value={profile.last_name} onIonInput={e=>setProfile({...profile,last_name:e.detail.value})}/>
            <IonInput fill="outline" label="E-Mail" labelPlacement="floating" value={profile.email} onIonInput={e=>setProfile({...profile,email:e.detail.value})}/>
            <IonInput fill="outline" label="Telefon" labelPlacement="floating" value={profile.phone} onIonInput={e=>setProfile({...profile,phone:e.detail.value})}/>
            <IonInput fill="outline" label="Personalnummer" labelPlacement="floating" value={profile.employee_number} onIonInput={e=>setProfile({...profile,employee_number:e.detail.value})}/>
            <IonSelect fill="outline" label="Beschäftigungsart" labelPlacement="floating" value={profile.employment_type} onIonChange={e=>setProfile({...profile,employment_type:e.detail.value})}><IonSelectOption value="minijob">Minijob</IonSelectOption><IonSelectOption value="teilzeit">Teilzeit</IonSelectOption><IonSelectOption value="vollzeit">Vollzeit</IonSelectOption><IonSelectOption value="student">Studentische Aushilfe</IonSelectOption></IonSelect>
            <IonInput type="number" fill="outline" label="Sollstunden / Monat" labelPlacement="floating" value={profile.monthly_hours} onIonInput={e=>setProfile({...profile,monthly_hours:e.detail.value})}/>
            <IonInput type="number" fill="outline" label="Tariflicher Stundenlohn" labelPlacement="floating" value={profile.tariff_hourly_rate} onIonInput={e=>setProfile({...profile,tariff_hourly_rate:e.detail.value})}/>
            <IonInput type="number" fill="outline" label="Übertarifliche Zulage" labelPlacement="floating" value={profile.extra_allowance} onIonInput={e=>setProfile({...profile,extra_allowance:e.detail.value})}/>
            <label className="akte-toggle">Aktiv <IonToggle checked={profile.active !== false} onIonChange={e=>setProfile({...profile,active:e.detail.checked})}/></label>
          </div>
          <h3 className="akte-subtitle">Personalstammdaten</h3>
          <div className="akte-form-grid">
            {[
              ['salutation','Anrede'],['street','Straße / Hausnummer'],['postal_code','PLZ'],['city','Ort'],['birth_date','Geburtsdatum'],['birth_name','Geburtsname'],['birth_place','Geburtsort'],['birth_country','Geburtsland'],['nationality','Staatsangehörigkeit'],['social_insurance_number','Sozialversicherungsnummer'],['health_insurance_name','Krankenkasse'],['insurance_type','Versicherungsart'],['tax_identification_number','Steuer-ID'],['tax_class','Steuerklasse'],['iban','IBAN'],['bank_account_holder','Kontoinhaber'],['bank_name','Bank'],['signature_place','Unterschriftsort'],
            ].map(([key,label]) => <IonInput key={key} fill="outline" type={key==='birth_date'?'date':'text'} label={label} labelPlacement="floating" value={master[key] || ''} onIonInput={e=>setMaster({...master,[key]:e.detail.value})}/>) }
          </div>
        </> : <div className="akte-form-grid">
          <IonInput fill="outline" label="Firmenname" labelPlacement="floating" value={profile.name} onIonInput={e=>setProfile({...profile,name:e.detail.value})}/>
          <IonInput fill="outline" label="Kundennummer" labelPlacement="floating" value={profile.customer_number} onIonInput={e=>setProfile({...profile,customer_number:e.detail.value})}/>
          <IonTextarea fill="outline" label="Anschrift" labelPlacement="floating" value={profile.address} onIonInput={e=>setProfile({...profile,address:e.detail.value})}/>
          <IonInput fill="outline" label="USt-IdNr." labelPlacement="floating" value={profile.vat_id} onIonInput={e=>setProfile({...profile,vat_id:e.detail.value})}/>
          <IonTextarea fill="outline" label="Interne Notizen" labelPlacement="floating" value={profile.notes} onIonInput={e=>setProfile({...profile,notes:e.detail.value})}/>
          <label className="akte-toggle">Aktiv <IonToggle checked={profile.active !== false} onIonChange={e=>setProfile({...profile,active:e.detail.checked})}/></label>
          <label className="akte-toggle">Verträge im Kundenportal sichtbar <IonToggle checked={profile.contract_visibility_enabled !== false} onIonChange={e=>setProfile({...profile,contract_visibility_enabled:e.detail.checked})}/></label>
          <IonInput fill="outline" label="Kontakt Vorname" labelPlacement="floating" value={profile.contact_first_name} onIonInput={e=>setProfile({...profile,contact_first_name:e.detail.value})}/>
          <IonInput fill="outline" label="Kontakt Nachname" labelPlacement="floating" value={profile.contact_last_name} onIonInput={e=>setProfile({...profile,contact_last_name:e.detail.value})}/>
          <IonInput fill="outline" label="Kontakt E-Mail" labelPlacement="floating" value={profile.contact_email} onIonInput={e=>setProfile({...profile,contact_email:e.detail.value})}/>
          <IonInput fill="outline" label="Kontakt Telefon" labelPlacement="floating" value={profile.contact_phone} onIonInput={e=>setProfile({...profile,contact_phone:e.detail.value})}/>
        </div>
      ) : (
        data.kind === 'worker' ? <div className="akte-detail-grid">
          <div><span>Name</span><b>{text(data.profile?.user_detail?.name)}</b></div><div><span>E-Mail</span><b>{text(data.profile?.user_detail?.email)}</b></div><div><span>Telefon</span><b>{text(data.profile?.user_detail?.phone)}</b></div><div><span>Personalnummer</span><b>{text(data.profile?.employee_number)}</b></div>
          <div><span>Beschäftigung</span><b>{text(data.profile?.employment_type)}</b></div><div><span>Sollstunden / Monat</span><b>{text(data.profile?.monthly_hours)}</b></div><div><span>Stundenlohn</span><b>{text(data.profile?.tariff_hourly_rate)} €</b></div><div><span>Zulage</span><b>{text(data.profile?.extra_allowance)} €</b></div>
          {Object.entries(data.master_data?.data || {}).map(([key,val]) => <div key={key}><span>{key.replaceAll('_',' ')}</span><b>{text(val)}</b></div>)}
        </div> : <div className="akte-detail-grid">
          <div><span>Firma</span><b>{text(data.profile?.name)}</b></div><div><span>Kundennummer</span><b>{text(data.profile?.customer_number)}</b></div><div><span>USt-IdNr.</span><b>{text(data.profile?.vat_id)}</b></div><div><span>Anschrift</span><b>{text(data.profile?.address)}</b></div>
          <div><span>Kontakt</span><b>{text(data.profile?.contacts_detail?.[0]?.name)}</b></div><div><span>E-Mail</span><b>{text(data.profile?.contacts_detail?.[0]?.email)}</b></div><div><span>Telefon</span><b>{text(data.profile?.contacts_detail?.[0]?.phone)}</b></div><div><span>Verträge sichtbar</span><b>{data.profile?.contract_visibility_enabled === false ? 'Nein' : 'Ja'}</b></div>
          <div className="wide"><span>Interne Notizen</span><b>{text(data.profile?.notes)}</b></div>
        </div>
      )}
    </section>

    <div className="akte-columns">
      <section className="akte-section"><div className="akte-section-head"><h2><IonIcon icon={documentTextOutline}/> Verträge</h2></div>{(data.contracts||[]).map(row=><div className="akte-row" key={row.id}><div><b>{row.title || row.template_name || 'Vertrag'}</b><span>{statusLabel[row.status] || row.status || '–'}{row.starts_on?` · ab ${formatDate(row.starts_on,false)}`:''}</span></div>{fileLink(row.pdf,'PDF')}</div>)}{!data.contracts?.length&&<div className="akte-empty">Noch keine Verträge.</div>}</section>
      <section className="akte-section"><div className="akte-section-head"><h2><IonIcon icon={folderOpenOutline}/> Dokumente</h2></div>{(data.document_folders||[]).map(folder=><div className="akte-folder" key={folder.key}><h3>{folder.label}<span>{folder.count}</span></h3>{folder.items.map(row=><div className="akte-row" key={row.id}><div><b>{row.title || 'Dokument'}</b><span>{formatDate(row.created_at)}</span></div>{fileLink(row.file)}</div>)}</div>)}{!data.document_folders?.length&&<div className="akte-empty">Noch keine Dokumente.</div>}</section>
    </div>

    {data.kind === 'worker' && <section className="akte-section"><div className="akte-section-head"><h2><IonIcon icon={receiptOutline}/> Lohnabrechnungen</h2></div><div className="akte-list-grid">{(data.payroll||[]).map(row=><div className="akte-row" key={row.id}><div><b>{row.period || 'Lohnabrechnung'}</b><span>{formatDate(row.created_at)}</span></div>{fileLink(row.document)}</div>)}{!data.payroll?.length&&<div className="akte-empty">Noch keine Lohnabrechnungen.</div>}</div></section>}

    {data.kind === 'client' && <div className="akte-columns"><section className="akte-section"><div className="akte-section-head"><h2><IonIcon icon={briefcaseOutline}/> Aufträge</h2></div>{(data.orders||[]).map(row=><div className="akte-row" key={row.id}><div><b>{row.title}</b><span>{statusLabel[row.status] || row.status} · {formatDate(row.starts_at)}</span></div></div>)}{!data.orders?.length&&<div className="akte-empty">Noch keine Aufträge.</div>}</section><section className="akte-section"><div className="akte-section-head"><h2>Einsatzorte</h2></div>{(data.locations||[]).map(row=><div className="akte-row" key={row.id}><div><b>{row.name}</b><span>{row.address}</span></div></div>)}{!data.locations?.length&&<div className="akte-empty">Noch keine Einsatzorte.</div>}</section></div>}

    <section className="akte-section"><div className="akte-section-head"><div><h2><IonIcon icon={calendarOutline}/> Einsätze</h2><p>Die zuletzt geplanten Einsätze dieser Akte.</p></div></div><div className="akte-shift-grid">{(data.shifts||[]).map(row=><div className="akte-shift" key={row.id}><strong>{row.position_name || 'Einsatz'}</strong><span>{formatDate(row.starts_at)} – {formatDate(row.ends_at)}</span><small>{row.location_name || 'Ohne Einsatzort'}{row.client_name?` · ${row.client_name}`:''}</small><IonBadge>{statusLabel[row.status] || row.status}</IonBadge></div>)}{!data.shifts?.length&&<div className="akte-empty">Noch keine Einsätze.</div>}</div></section>
  </div>;
}

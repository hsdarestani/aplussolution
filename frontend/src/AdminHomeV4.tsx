import React, { useEffect, useMemo, useState } from 'react';
import { IonBadge, IonButton, IonIcon, IonInput, IonSpinner } from '@ionic/react';
import {
  alertCircleOutline,
  briefcaseOutline,
  calendarOutline,
  checkmarkCircleOutline,
  documentTextOutline,
  peopleOutline,
  refreshOutline,
  notificationsOutline,
  syncOutline,
  timeOutline,
  walletOutline,
} from 'ionicons/icons';
import { api } from './api';
import './admin-home-v4.css';

type Navigate = (view: any) => void;

type ExceptionItem = {
  category: string;
  severity: 'critical' | 'warning' | 'info';
  title: string;
  message: string;
  view: string;
  object_id?: string;
  due_at?: string;
  meta?: Record<string, any>;
};

type MobileDashboard = {
  attendance_notices?: number;
  time_off_requests?: number;
  shift_requests?: number;
  open_shift_requests?: number;
  open_shifts_available?: number;
  source?: string;
  sync_enabled?: boolean;
  read_only?: boolean;
};

const categoryLabels: Record<string, string> = {
  all: 'Alle',
  staffing: 'Besetzung',
  attendance: 'Arbeitszeit',
  contracts: 'Verträge',
  documents: 'Personalakte',
  integrations: 'Integrationen',
  requests: 'Anträge',
};

const categoryIcons: Record<string, string> = {
  staffing: peopleOutline,
  attendance: timeOutline,
  contracts: documentTextOutline,
  documents: briefcaseOutline,
  integrations: syncOutline,
  requests: calendarOutline,
};

const severityText: Record<string, string> = {
  critical: 'Kritisch',
  warning: 'Warnung',
  info: 'Hinweis',
};

const priorityActions = [
  { view: 'schedule', label: 'Dienstplan', hint: 'OpenShifts & Besetzung', icon: calendarOutline },
  { view: 'time', label: 'Zeiterfassung', hint: 'Zeiten prüfen', icon: timeOutline },
  { view: 'operations', label: 'Lohn & Anfragen', hint: 'Freigaben, Saldo & Berichte', icon: walletOutline },
  { view: 'people', label: 'Personal & Kunden', hint: 'Stammdaten & Zugänge', icon: peopleOutline },
  { view: 'messages', label: 'Mitteilungen', hint: 'Hinweise an Mitarbeiter senden', icon: notificationsOutline },
];

function dueText(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function AdminHomeV4({ navigate }: { navigate: Navigate }) {
  const [data, setData] = useState<any>();
  const [mobileDashboard, setMobileDashboard] = useState<MobileDashboard>();
  const [category, setCategory] = useState('all');
  const [severity, setSeverity] = useState('all');
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setBusy(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (category !== 'all') params.set('category', category);
      if (severity !== 'all') params.set('severity', severity);
      if (query.trim()) params.set('q', query.trim());
      params.set('limit', '120');
      const [exceptionData, dashboardData] = await Promise.all([
        api(`admin/exceptions/?${params.toString()}`),
        api('admin/mobile-dashboard/').catch(() => undefined),
      ]);
      setData(exceptionData);
      if (dashboardData) setMobileDashboard(dashboardData);
    } catch (reason: any) {
      setError(reason.message || 'Handlungsbedarf konnte nicht geladen werden.');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), query ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [category, severity, query]);

  useEffect(() => {
    const refresh = () => { void load(); };
    const refreshWhenVisible = () => { if (document.visibilityState === 'visible') refresh(); };
    const interval = window.setInterval(refresh, 30000);
    window.addEventListener('focus', refresh);
    window.addEventListener('aplus:dashboard-invalidated', refresh);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener('focus', refresh);
      window.removeEventListener('aplus:dashboard-invalidated', refresh);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [category, severity, query]);

  const results: ExceptionItem[] = data?.results || [];
  const summary = data?.summary || {};
  const byCategory = summary.by_category || {};
  const criticalFirst = useMemo(() => results.filter((item) => item.severity === 'critical'), [results]);

  const count = (key: keyof MobileDashboard, fallback = 0) => {
    const value = mobileDashboard?.[key];
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
  };

  const attendanceNotices = count('attendance_notices', byCategory.attendance || 0);
  const timeOffRequests = count('time_off_requests', byCategory.requests || 0);
  const shiftRequests = count('shift_requests', 0);
  const openShiftRequests = count('open_shift_requests', 0);
  const openShiftsAvailable = count('open_shifts_available', byCategory.staffing || 0);

  function open(item: ExceptionItem) {
    sessionStorage.setItem('aplus:focus', JSON.stringify({ view: item.view, id: item.object_id, category: item.category }));
    navigate(item.view);
  }

  return (
    <div className="admin-home-v4" data-testid="admin-exception-center">
      <div className="wiw-mobile-admin-dashboard" data-testid="wiw-mobile-admin-dashboard">
        <div className="wiw-section-label">Heute</div>
        <button type="button" className="wiw-mobile-row" aria-label="Arbeitszeit-Hinweise" onClick={() => navigate('time')}><span className="wiw-count">{attendanceNotices}</span><strong>Arbeitszeit-Hinweise</strong></button>
        <button type="button" className="wiw-mobile-row" aria-label="Mitarbeiteraktivität" onClick={() => navigate('people')}><span className="wiw-row-icon"><IonIcon icon={peopleOutline}/></span><strong>Mitarbeiteraktivität</strong></button>

        <div className="wiw-section-label">Anfragen</div>
        <button type="button" className="wiw-mobile-row" aria-label="Abwesenheitsanträge" onClick={() => navigate('operations')}><span className="wiw-count">{timeOffRequests}</span><strong>Abwesenheitsanträge</strong></button>
        <button type="button" className="wiw-mobile-row" aria-label="Schichtanfragen" onClick={() => navigate('operations')}><span className="wiw-count">{shiftRequests}</span><strong>Schichtanfragen</strong></button>
        <button type="button" className="wiw-mobile-row" aria-label="OpenShift-Anfragen" onClick={() => navigate('schedule')}><span className="wiw-count">{openShiftRequests}</span><strong>OpenShift-Anfragen</strong></button>

        <div className="wiw-section-label">Dienstplan</div>
        <button type="button" className="wiw-next-shift" aria-label="Dienstplan öffnen" onClick={() => navigate('schedule')}><small>Nächster Einsatz:</small><strong>Dienstplan öffnen</strong></button>
        <button type="button" className="wiw-mobile-row" aria-label="Schichten" onClick={() => navigate('schedule')}><span className="wiw-row-icon"><IonIcon icon={calendarOutline}/></span><strong>Schichten</strong></button>
        <button type="button" className="wiw-mobile-row" aria-label="OpenShifts verfügbar" onClick={() => navigate('schedule')}><span className="wiw-count">{openShiftsAvailable}</span><strong>OpenShifts verfügbar</strong></button>

        <div className="wiw-section-label">Wichtige anstehende Termine</div>
        <div className="wiw-upcoming"><div>{(criticalFirst[0] || results[0]) ? <><strong>{(criticalFirst[0] || results[0]).title}</strong><span>{(criticalFirst[0] || results[0]).message}</span></> : <span>Keine offenen Vorgänge</span>}</div>{(criticalFirst[0] || results[0]) && <button type="button" onClick={() => open(criticalFirst[0] || results[0])}>Öffnen</button>}</div>
      </div>
      <section className="admin-attention-hero">
        <div>
          <small>ADMIN · HANDLUNGSBEDARF</small>
          <h1>Nur das, was heute Aufmerksamkeit braucht.</h1>
          <p>Keine allgemeine KPI-Wand. Offene Besetzung, fehlende Check-ins, Vertragsfristen, unvollständige Akten und technische Fehler – nach Dringlichkeit sortiert.</p>
        </div>
        <IonButton fill="outline" disabled={busy} onClick={() => void load()}>
          <IonIcon slot="start" icon={refreshOutline} />
          Aktualisieren
        </IonButton>
      </section>

      <section className="admin-priority-section" data-testid="admin-priority-actions" aria-label="Wichtigste tägliche Funktionen">
        <div className="admin-priority-heading">
          <div><small>SCHNELLZUGRIFF</small><h2>Tägliche Arbeit</h2></div>
          <span>Die 5 wichtigsten Bereiche direkt erreichbar.</span>
        </div>
        <div className="admin-priority-actions">
          {priorityActions.map((item, index) => (
            <button type="button" key={item.view} onClick={() => navigate(item.view)} aria-label={item.label}>
              <span className="admin-priority-index">{String(index + 1).padStart(2, '0')}</span>
              <IonIcon icon={item.icon} />
              <strong>{item.label}</strong>
              <small>{item.hint}</small>
            </button>
          ))}
        </div>
      </section>

      <div className="attention-summary">
        <SummaryCard label="Kritisch" value={summary.critical || 0} tone="critical" />
        <SummaryCard label="Warnungen" value={summary.warning || 0} tone="warning" />
        <SummaryCard label="Besetzung" value={byCategory.staffing || 0} />
        <SummaryCard label="Arbeitszeit" value={byCategory.attendance || 0} />
        <SummaryCard label="Verträge" value={byCategory.contracts || 0} />
      </div>

      <section className="attention-toolbar">
        <div className="attention-categories" aria-label="Handlungsbedarf filtern">
          {Object.keys(categoryLabels).map((key) => (
            <button
              type="button"
              key={key}
              className={category === key ? 'active' : ''}
              onClick={() => setCategory(key)}
            >
              {categoryLabels[key]}
              {key !== 'all' && <span>{byCategory[key] || 0}</span>}
            </button>
          ))}
        </div>
        <div className="attention-filter-row">
          <IonInput
            fill="outline"
            className="attention-query"
            placeholder="In offenen Vorgängen suchen …"
            value={query}
            onIonInput={(event) => setQuery(String(event.detail.value || ''))}
          />
          <div className="severity-switch" aria-label="Dringlichkeit">
            {['all', 'critical', 'warning', 'info'].map((key) => (
              <button type="button" key={key} className={severity === key ? 'active' : ''} onClick={() => setSeverity(key)}>
                {key === 'all' ? 'Alle' : severityText[key]}
              </button>
            ))}
          </div>
        </div>
      </section>

      {error && <div className="attention-error">{error}</div>}
      {!data && busy && <div className="attention-loading"><IonSpinner /><span>Handlungsbedarf wird geladen …</span></div>}

      {criticalFirst.length > 0 && category === 'all' && severity === 'all' && !query && (
        <section className="critical-strip">
          <IonIcon icon={alertCircleOutline} />
          <div><b>{criticalFirst.length} kritische Vorgänge</b><span>Diese Punkte sollten zuerst bearbeitet werden.</span></div>
        </section>
      )}

      <section className="attention-list">
        {results.map((item, index) => (
          <article className={`attention-item severity-${item.severity}`} key={`${item.category}-${item.object_id || index}-${item.title}`}>
            <span className="severity-mark" aria-hidden="true" />
            <div className="attention-item-icon"><IonIcon icon={categoryIcons[item.category] || alertCircleOutline} /></div>
            <div className="attention-item-copy">
              <div className="attention-item-topline">
                <IonBadge color={item.severity === 'critical' ? 'danger' : item.severity === 'warning' ? 'warning' : 'medium'}>
                  {severityText[item.severity]}
                </IonBadge>
                <span>{categoryLabels[item.category] || item.category}</span>
                {item.due_at && <span>· {dueText(item.due_at)}</span>}
              </div>
              <h3>{item.title}</h3>
              <p>{item.message}</p>
              {!!item.meta?.open_count && <small>{item.meta.filled_count || 0}/{item.meta.required_count || 0} besetzt</small>}
            </div>
            <IonButton size="small" fill={item.severity === 'critical' ? 'solid' : 'outline'} onClick={() => open(item)}>
              Öffnen
            </IonButton>
          </article>
        ))}

        {data && !results.length && (
          <div className="attention-empty">
            <IonIcon icon={checkmarkCircleOutline} />
            <h2>Keine offenen Ausnahmen.</h2>
            <p>Für die aktuelle Auswahl gibt es nichts zu bearbeiten.</p>
          </div>
        )}
      </section>
    </div>
  );
}

function SummaryCard({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return <div className={`attention-summary-card ${tone || ''}`}><small>{label}</small><strong>{value}</strong></div>;
}

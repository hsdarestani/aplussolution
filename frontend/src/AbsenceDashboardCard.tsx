import React, { useEffect, useState } from 'react';
import { IonBadge, IonButton, IonIcon, IonSpinner } from '@ionic/react';
import { alertCircleOutline, peopleOutline } from 'ionicons/icons';
import { apiAll } from './api';
import './absence-dashboard.css';

const active = new Set(['reported', 'coverage_pending', 'offered', 'moved_to_open']);
const urgentAt = (item: any, now: number) => {
  const start = new Date(item.shift_starts_at).getTime();
  const end = item.shift_ends_at ? new Date(item.shift_ends_at).getTime() : Number.POSITIVE_INFINITY;
  return Number.isFinite(start) && start <= now + 24 * 60 * 60 * 1000 && end >= now;
};

export default function AbsenceDashboardCard({ navigate }: { navigate: (view: any) => void }) {
  const [cases, setCases] = useState<any[]>();
  const [error, setError] = useState('');
  const [clock, setClock] = useState(Date.now());

  useEffect(() => {
    apiAll('absence-cases/?ordering=-reported_at')
      .then((rows) => setCases(rows.filter((item: any) => active.has(item.status))))
      .catch((reason: any) => setError(reason.message || 'Ausfälle konnten nicht geladen werden.'));
  }, []);
  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const urgent = cases?.filter((item) => urgentAt(item, clock)).length || 0;
  const movedToOpen = cases?.filter((item) => item.status === 'moved_to_open').length || 0;
  return <section className={`absence-dashboard-card ${urgent ? 'urgent' : ''}`} data-testid="absence-dashboard-card">
    <div className="absence-dashboard-icon"><IonIcon icon={urgent ? alertCircleOutline : peopleOutline}/></div>
    <div className="absence-dashboard-copy">
      <div className="absence-dashboard-top"><small>AUSFALL & ERSATZ</small>{urgent > 0 && <IonBadge color="danger">{urgent} ≤ 24h</IonBadge>}</div>
      {!cases && !error ? <div className="absence-dashboard-loading"><IonSpinner name="dots"/> Wird geladen …</div> : error ? <p>{error}</p> : <><h3>{cases?.length || 0} offene Ausfälle</h3><p>{movedToOpen ? `${movedToOpen} Ersatzplätze sind bereits als OpenShift veröffentlicht.` : 'Offene Fälle direkt in der Disposition bearbeiten.'}</p></>}
    </div>
    <IonButton size="small" fill={urgent ? 'solid' : 'outline'} color={urgent ? 'danger' : 'primary'} onClick={() => navigate('operations')}>Bearbeiten</IonButton>
  </section>;
}

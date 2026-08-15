import React, { useEffect, useState } from 'react';
import { IonBadge, IonButton, IonIcon, IonSpinner } from '@ionic/react';
import { alertCircleOutline, peopleOutline } from 'ionicons/icons';
import { apiAll } from './api';
import './absence-dashboard.css';

const active = new Set(['reported', 'coverage_pending', 'offered', 'moved_to_open']);

export default function AbsenceDashboardCard({ navigate }: { navigate: (view: any) => void }) {
  const [cases, setCases] = useState<any[]>();
  const [error, setError] = useState('');

  useEffect(() => {
    apiAll('absence-cases/?ordering=-reported_at')
      .then((rows) => setCases(rows.filter((item: any) => active.has(item.status))))
      .catch((reason: any) => setError(reason.message || 'Ausfälle konnten nicht geladen werden.'));
  }, []);

  const shortNotice = cases?.filter((item) => item.short_notice).length || 0;
  const movedToOpen = cases?.filter((item) => item.status === 'moved_to_open').length || 0;
  return <section className={`absence-dashboard-card ${shortNotice ? 'urgent' : ''}`} data-testid="absence-dashboard-card">
    <div className="absence-dashboard-icon"><IonIcon icon={shortNotice ? alertCircleOutline : peopleOutline}/></div>
    <div className="absence-dashboard-copy">
      <div className="absence-dashboard-top"><small>AUSFALL & ERSATZ</small>{shortNotice > 0 && <IonBadge color="danger">{shortNotice} kurzfristig</IonBadge>}</div>
      {!cases && !error ? <div className="absence-dashboard-loading"><IonSpinner name="dots"/> Wird geladen …</div> : error ? <p>{error}</p> : <><h3>{cases?.length || 0} offene Ausfälle</h3><p>{movedToOpen ? `${movedToOpen} Ersatzplätze sind bereits als OpenShift veröffentlicht.` : 'Offene Fälle direkt in der Disposition bearbeiten.'}</p></>}
    </div>
    <IonButton size="small" fill={shortNotice ? 'solid' : 'outline'} color={shortNotice ? 'danger' : 'primary'} onClick={() => navigate('operations')}>Bearbeiten</IonButton>
  </section>;
}

import React, { useState } from 'react';
import { IonLabel, IonSegment, IonSegmentButton } from '@ionic/react';
import type { User } from './api';
import AttendanceV4 from './AttendanceV4';
import PayrollCenter from './PayrollCenter';

export default function AttendanceV3({ user }: { user: User }) {
  const [tab, setTab] = useState<'attendance' | 'payroll'>('attendance');
  return <>
    <div className="time-workspace-tabs">
      <IonSegment aria-label="Arbeitszeitbereiche" value={tab} onIonChange={(event) => setTab(String(event.detail.value) as 'attendance' | 'payroll')}>
        <IonSegmentButton value="attendance"><IonLabel>Zeiterfassung</IonLabel></IonSegmentButton>
        <IonSegmentButton value="payroll"><IonLabel>Abrechnung</IonLabel></IonSegmentButton>
      </IonSegment>
    </div>
    {tab === 'attendance' ? <AttendanceV4 user={user} /> : <PayrollCenter user={user} />}
  </>;
}

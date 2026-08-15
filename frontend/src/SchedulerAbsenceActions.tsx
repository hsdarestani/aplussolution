import React, { useMemo, useState } from 'react';
import { IonButton, IonModal, IonSelect, IonSelectOption, IonSpinner, IonTextarea, IonToast } from '@ionic/react';
import { api, User } from './api';

const val = (event: any) => event.detail.value ?? '';
const managerRole = (user: User) => ['admin', 'manager'].includes(user.role);

export default function SchedulerAbsenceActions({ user, shift, onChanged }: { user: User; shift: any; onChanged: () => void | Promise<void> }) {
  const manager = managerRole(user);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [kind, setKind] = useState(manager ? 'no_show' : 'sick');
  const [note, setNote] = useState('');
  const [slot, setSlot] = useState('');
  const assignments = useMemo(() => shift.assignments || [], [shift.assignments]);
  const endedLongAgo = new Date(shift.ends_at).getTime() < Date.now() - 24 * 60 * 60 * 1000;

  if (user.role === 'client' || endedLongAgo || (manager && assignments.length === 0)) return null;

  async function submit() {
    const assignment = manager ? assignments.find((item: any) => String(item.slot) === slot) : assignments[0];
    if (manager && !assignment) {
      setToast('Bitte einen belegten Personalplatz auswählen.');
      return;
    }
    setBusy(true);
    try {
      await api('operations/callouts/report/', {
        method: 'POST',
        body: JSON.stringify({
          shift: shift.id,
          slot: assignment?.slot,
          worker: manager ? assignment?.worker : undefined,
          kind,
          note,
        }),
      });
      setOpen(false);
      setSlot('');
      setNote('');
      setKind(manager ? 'no_show' : 'sick');
      setToast('Ausfall wurde erfasst.');
      await onChanged();
    } catch (error: any) {
      setToast(error.message);
    } finally {
      setBusy(false);
    }
  }

  return <>
    <IonButton size="small" fill="outline" color="danger" disabled={busy} onClick={() => setOpen(true)}>{manager ? 'Ausfall' : 'Ausfall melden'}</IonButton>
    <IonModal isOpen={open} onDidDismiss={() => setOpen(false)}>
      <div className="sv2-modal">
        <div className="sv2-modal-head"><div><small>AUSFALL & ERSATZ</small><h2>{manager ? 'Ausfall erfassen' : 'Ausfall melden'}</h2><p>{shift.position_name} · {shift.location_name}</p></div><IonButton fill="clear" onClick={() => setOpen(false)}>Schließen</IonButton></div>
        <div className="sv2-form">
          {manager && <IonSelect className="full" fill="outline" label="Mitarbeiter *" labelPlacement="floating" value={slot} onIonChange={(event) => setSlot(String(val(event)))}>{assignments.map((assignment: any) => <IonSelectOption key={assignment.slot} value={assignment.slot}>{assignment.worker_name}</IonSelectOption>)}</IonSelect>}
          <IonSelect className="full" fill="outline" label="Grund" labelPlacement="floating" value={kind} onIonChange={(event) => setKind(String(val(event)))}>
            <IonSelectOption value="sick">Krank</IonSelectOption>
            <IonSelectOption value="emergency">Notfall</IonSelectOption>
            <IonSelectOption value="personal">Persönlich verhindert</IonSelectOption>
            {manager && <IonSelectOption value="no_show">Nicht erschienen</IonSelectOption>}
            <IonSelectOption value="other">Sonstiger Ausfall</IonSelectOption>
          </IonSelect>
          <IonTextarea className="full" fill="outline" label="Hinweis" labelPlacement="floating" value={note} onIonInput={(event) => setNote(String(val(event)))}/>
        </div>
        <div className="sv2-modal-actions"><IonButton fill="outline" onClick={() => setOpen(false)}>Abbrechen</IonButton><IonButton color="danger" disabled={busy || (manager && !slot)} onClick={() => void submit()}>{busy ? <IonSpinner name="dots"/> : 'Ausfall bestätigen'}</IonButton></div>
      </div>
    </IonModal>
    <IonToast isOpen={!!toast} message={toast} duration={4000} onDidDismiss={() => setToast('')}/>
  </>;
}

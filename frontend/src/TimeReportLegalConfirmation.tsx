import React from 'react';
import { createPortal } from 'react-dom';
import './time-report-legal.css';

export const TIME_REPORT_LEGAL_TEXT = 'Mit dem Absenden bestätige ich, dass die von mir angegebenen Arbeits-, Beginn und Endzeiten vollständig und wahrheitsgemäß sind.\n\nMir ist bekannt, dass bewusst falsche Angaben arbeitsrechtliche Konsequenzen bis hin zur Kündigung nach sich ziehen können. Bei schuldhaft verursachten Schäden bleiben Schadensersatzansprüche des Arbeitgebers vorbehalten.';

export default function TimeReportLegalConfirmation({
  open,
  busy,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!open || typeof document === 'undefined') return null;
  return createPortal(
    <div className="time-report-legal-backdrop" role="presentation" onClick={() => !busy && onCancel()}>
      <section className="time-report-legal-card" role="dialog" aria-modal="true" aria-labelledby="time-report-legal-title" onClick={(event) => event.stopPropagation()}>
        <small>RECHTLICHE BESTÄTIGUNG</small>
        <h2 id="time-report-legal-title">Arbeitszeit verbindlich bestätigen</h2>
        <p>{TIME_REPORT_LEGAL_TEXT}</p>
        <div>
          <button type="button" disabled={busy} onClick={onCancel}>Zurück</button>
          <button type="button" className="primary" disabled={busy} onClick={onConfirm}>{busy ? 'Wird gesendet …' : 'Bestätigen & senden'}</button>
        </div>
      </section>
    </div>,
    document.body,
  );
}

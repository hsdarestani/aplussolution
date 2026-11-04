import React, { useState } from 'react';
import { api } from './api';

type Preview = {
  matched_worker: string;
  profile: Record<string, unknown>;
  master_data: Record<string, unknown>;
  warnings: string[];
};

export default function PersonnelPdfImport({
  workerId, onImported,
}: {
  workerId: string;
  onImported: (preview: Preview) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function importFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = '';
    if (!file || busy) return;
    setError('');
    setBusy(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const preview = await api<Preview>(`workers/${workerId}/personalfragebogen/preview/`, {
        method: 'POST',
        body: form,
      });
      if (preview.matched_worker !== workerId) throw new Error('Mitarbeiter-ID stimmt nicht überein.');
      onImported(preview);
    } catch (e: any) {
      setError(e?.message || 'Personalfragebogen konnte nicht gelesen werden.');
    } finally {
      setBusy(false);
    }
  }

  return <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
    <label className="akte-back" style={{ cursor: busy ? 'wait' : 'pointer', display: 'inline-flex', gap: 8, alignItems: 'center' }}>
      {busy ? 'Liest Personalfragebogen …' : 'Personalfragebogen PDF einlesen'}
      <input
        type="file"
        accept=".pdf,application/pdf"
        disabled={busy}
        onChange={event => { void importFile(event); }}
        style={{ position: 'absolute', width: 1, height: 1, opacity: 0 }}
        aria-label="Personalfragebogen als PDF auswählen"
      />
    </label>
    {error && <span role="alert" style={{ color: '#b42318', fontSize: 12 }}>{error}</span>}
  </div>;
}

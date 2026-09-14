import fs from 'node:fs';
import path from 'node:path';

const file = path.resolve('src/WiwEmployeeScheduleMobile.tsx');
let source = fs.readFileSync(file, 'utf8');

function replaceOnce(before, after, label) {
  if (source.includes(after)) return;
  if (!source.includes(before)) {
    throw new Error(`Service Zeitplan patch failed: ${label}`);
  }
  source = source.replace(before, after);
}

replaceOnce(
`function hours(shift: any) {
  const gross = Math.max(0, (new Date(shift.ends_at).getTime() - new Date(shift.starts_at).getTime()) / 3600000);
  return Math.max(0, gross - Number(shift.break_minutes || 0) / 60);
}
`,
`function hours(shift: any) {
  const gross = Math.max(0, (new Date(shift.ends_at).getTime() - new Date(shift.starts_at).getTime()) / 3600000);
  return Math.max(0, gross - Number(shift.break_minutes || 0) / 60);
}
function shortPersonName(value: string) {
  const parts = String(value || '').trim().split(/\\s+/).filter(Boolean);
  if (parts.length <= 1) return parts[0] || '';
  return parts[0] + ' ' + parts.slice(1).map((part) => part.charAt(0) + '.').join(' ');
}
function assignedNames(shift: any) {
  const names = (shift?.assigned_workers || [])
    .map((assigned: any) => shortPersonName(assigned?.name || ''))
    .filter(Boolean);
  return names.join(', ');
}
function isOwnShift(shift: any) {
  return Boolean((shift?.assigned_workers || []).some((assigned: any) => assigned?.is_me));
}
`,
'helpers',
);

replaceOnce(
`  const [mode, setMode] = useState<Mode>('mine');
  const [mine, setMine] = useState<any[]>([]);`,
`  const [mode, setMode] = useState<Mode>('mine');
  const [serviceSchedule, setServiceSchedule] = useState(false);
  const [mine, setMine] = useState<any[]>([]);`,
'service state',
);

replaceOnce(
`      const [mineData, openData] = await Promise.all([
        api('shifts/mine/?ordering=starts_at'),
        api('shifts/available/?ordering=starts_at'),
      ]);
      const nextMine = unpack(mineData);
      const nextOpen = unpack(openData);
      setMine(nextMine);`,
`      const [mineData, openData] = await Promise.all([
        api('employee/schedule/?ordering=starts_at'),
        api('shifts/available/?ordering=starts_at'),
      ]);
      const nextMine = Array.isArray(mineData?.shifts) ? mineData.shifts : unpack(mineData);
      const nextOpen = unpack(openData);
      setServiceSchedule(Boolean(mineData?.service_schedule));
      setMine(nextMine);`,
'employee schedule endpoint',
);

replaceOnce(
`  const totalHours = useMemo(() => rows.reduce((sum, shift) => sum + hours(shift), 0), [rows]);`,
`  const totalHours = useMemo(() => (mode === 'mine' ? rows.filter(isOwnShift) : rows).reduce((sum, shift) => sum + hours(shift), 0), [mode, rows]);`,
'own total hours',
);

replaceOnce(
`        <DetailRow icon={personOutline}>{mode === 'mine' ? (worker.name || worker.email || 'Mitarbeiter') : 'OpenShift'}</DetailRow>`,
`        <DetailRow icon={personOutline}>{mode === 'mine' ? (assignedNames(selected) || worker.name || worker.email || 'Mitarbeiter') : 'OpenShift'}</DetailRow>`,
'detail worker names',
);

replaceOnce(
`        {mode === 'open' ? (
          <button type="button" className="primary" disabled={busy} onClick={() => void claim(selected)}>{busy ? 'Bitte warten …' : 'Schicht übernehmen'}</button>
        ) : selected.my_release_request?.status === 'pending' ? (`,
`        {mode === 'open' ? (
          <button type="button" className="primary" disabled={busy} onClick={() => void claim(selected)}>{busy ? 'Bitte warten …' : 'Schicht übernehmen'}</button>
        ) : !isOwnShift(selected) ? (
          <button type="button" disabled>Nur sichtbar · Service Zeitplan</button>
        ) : selected.my_release_request?.status === 'pending' ? (`,
'peer shift action guard',
);

replaceOnce(
`        <IonSegmentButton value="mine"><IonLabel>Meine Schichten</IonLabel></IonSegmentButton>`,
`        <IonSegmentButton value="mine"><IonLabel>{serviceSchedule ? 'Service Zeitplan' : 'Meine Schichten'}</IonLabel></IonSegmentButton>`,
'tab label',
);

replaceOnce(
`            <p>{mode === 'mine' ? (worker.name || worker.email || 'Mitarbeiter') : 'OpenShift'}</p>`,
`            <p>{mode === 'mine' ? (assignedNames(shift) || worker.name || worker.email || 'Mitarbeiter') : 'OpenShift'}</p>`,
'card worker names',
);

replaceOnce(
`        {!groupedRows.length && <div className="wiw-employee-day-empty">{busy ? 'Schichten werden geladen …' : mode === 'open' ? 'Keine verfügbaren OpenShifts' : 'Keine eigenen Schichten'}</div>}`,
`        {!groupedRows.length && <div className="wiw-employee-day-empty">{busy ? 'Schichten werden geladen …' : mode === 'open' ? 'Keine verfügbaren OpenShifts' : serviceSchedule ? 'Keine Schichten im Service Zeitplan' : 'Keine eigenen Schichten'}</div>}`,
'empty label',
);

replaceOnce(
`      {mode === 'mine' && <div className="wiw-employee-week-total" data-testid="shift-list-total"><span>Gesamtstunden</span><strong>{totalHours.toFixed(1)}</strong></div>}`,
`      {mode === 'mine' && <div className="wiw-employee-week-total" data-testid="shift-list-total"><span>{serviceSchedule ? 'Eigene Gesamtstunden' : 'Gesamtstunden'}</span><strong>{totalHours.toFixed(1)}</strong></div>}`,
'total label',
);

fs.writeFileSync(file, source);
console.log('Applied Service Zeitplan worker visibility patch.');

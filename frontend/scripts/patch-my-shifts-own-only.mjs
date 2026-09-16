import { readFileSync, writeFileSync } from 'node:fs';

function patchOnce(source, before, after, label) {
  if (source.includes(after)) return source;
  if (!source.includes(before)) {
    throw new Error(`${label} marker changed; update patch-my-shifts-own-only.mjs.`);
  }
  return source.replace(before, after);
}

// "Meine Schichten" is a personal shortcut. Service employees can still use the
// normal Dienstplan entry to see the shared Service Zeitplan, but this dashboard
// shortcut must explicitly request the personal scope.
const homePath = new URL('../src/EmployeeHome.tsx', import.meta.url);
const homeSource = readFileSync(homePath, 'utf8');
const legacyMineRow = `      <MobileRow icon={calendarOutline} label="Meine Schichten" onClick={()=>navigate('schedule')}/>`;
const scopedMineRow = `      <MobileRow icon={calendarOutline} label="Meine Schichten" onClick={()=>{sessionStorage.setItem('aplus:schedule-entry-filter','mine');navigate('schedule');}}/>`;
const homeNext = patchOnce(homeSource, legacyMineRow, scopedMineRow, 'EmployeeHome Meine Schichten');
if (homeNext !== homeSource) writeFileSync(homePath, homeNext);

// employee/schedule intentionally returns the complete Service Zeitplan for
// service workers. Keep that shared view intact and filter it client-side only
// when the user entered through the personal "Meine Schichten" shortcut.
const schedulePath = new URL('../src/WiwEmployeeScheduleMobile.tsx', import.meta.url);
const scheduleSource = readFileSync(schedulePath, 'utf8');
let scheduleNext = scheduleSource;

const legacyState = `  const [serviceSchedule, setServiceSchedule] = useState(false);\n  const [mine, setMine] = useState<any[]>([]);`;
const scopedState = `  const [serviceSchedule, setServiceSchedule] = useState(false);\n  const [ownOnly, setOwnOnly] = useState(false);\n  const [mine, setMine] = useState<any[]>([]);`;
scheduleNext = patchOnce(scheduleNext, legacyState, scopedState, 'employee schedule own-only state');

const legacyEntry = `    const requested = sessionStorage.getItem('aplus:schedule-entry-filter');\n    sessionStorage.removeItem('aplus:schedule-entry-filter');\n    setMode(requested === 'open' ? 'open' : 'mine');`;
const scopedEntry = `    const requested = sessionStorage.getItem('aplus:schedule-entry-filter');\n    sessionStorage.removeItem('aplus:schedule-entry-filter');\n    if (requested === 'open') {\n      setMode('open');\n      setOwnOnly(false);\n    } else {\n      setMode('mine');\n      setOwnOnly(requested === 'mine');\n    }`;
scheduleNext = patchOnce(scheduleNext, legacyEntry, scopedEntry, 'employee schedule entry scope');

const legacyRows = `  const rows = mode === 'mine' ? mine : open;`;
const scopedRows = `  const rows = mode === 'mine' ? (ownOnly ? mine.filter(isOwnShift) : mine) : open;`;
scheduleNext = patchOnce(scheduleNext, legacyRows, scopedRows, 'employee schedule own-only rows');

const legacyMineTab = `          <button type="button" role="tab" aria-selected={mode === 'mine'} className={mode === 'mine' ? 'active' : ''} onClick={() => setMode('mine')}>{serviceSchedule ? 'Service Zeitplan' : 'Meine Schichten'}</button>`;
const scopedMineTabs = `          {serviceSchedule ? <>\n            <button type="button" role="tab" aria-selected={mode === 'mine' && ownOnly} className={mode === 'mine' && ownOnly ? 'active' : ''} onClick={() => { setMode('mine'); setOwnOnly(true); }}>Meine Schichten</button>\n            <button type="button" role="tab" aria-selected={mode === 'mine' && !ownOnly} className={mode === 'mine' && !ownOnly ? 'active' : ''} onClick={() => { setMode('mine'); setOwnOnly(false); }}>Service Zeitplan</button>\n          </> : <button type="button" role="tab" aria-selected={mode === 'mine'} className={mode === 'mine' ? 'active' : ''} onClick={() => { setMode('mine'); setOwnOnly(true); }}>Meine Schichten</button>}`;
scheduleNext = patchOnce(scheduleNext, legacyMineTab, scopedMineTabs, 'employee schedule tabs');

if (scheduleNext !== scheduleSource) writeFileSync(schedulePath, scheduleNext);

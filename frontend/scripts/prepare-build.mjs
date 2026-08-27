import { readFileSync, writeFileSync } from 'node:fs';

const appPath = new URL('../src/App.tsx', import.meta.url);
const appSource = readFileSync(appPath, 'utf8');
let appNext = appSource;

const originalColor = `          type="color"
          label="Farbe"`;
const compatibleColor = `          {...({ type: 'color' } as any)}
          label="Farbe"`;

if (appNext.includes(originalColor)) {
  appNext = appNext.replace(originalColor, compatibleColor);
}

const localDateTime = "const dateTime = (input?: string) => (input ? new Date(input).toLocaleString('de-DE') : '–');";
const berlinDateTime = `const BUSINESS_TIME_ZONE = 'Europe/Berlin';
const dateTime = (input?: string) =>
  input ? new Date(input).toLocaleString('de-DE', { timeZone: BUSINESS_TIME_ZONE }) : '–';`;

if (appNext.includes(localDateTime)) {
  appNext = appNext.replace(localDateTime, berlinDateTime);
} else if (!appNext.includes("const BUSINESS_TIME_ZONE = 'Europe/Berlin';")) {
  throw new Error('Legacy App.tsx dateTime helper marker changed; update prepare-build.mjs.');
}

// The backend is the source of truth for document lifecycle actions. Never show
// an action that contract_readiness will reject, and never offer a signature role
// that the selected document does not require.
const legacyGenerateButton = `                {contract.status === 'draft' && (
                  <IonButton size="small" fill="outline" onClick={() => contractAction(contract.id, 'generate_pdf')}>
                    PDF erstellen
                  </IonButton>
                )}`;
const readinessGenerateButton = `                {contract.readiness?.generation_allowed && (
                  <IonButton size="small" fill="outline" onClick={() => contractAction(contract.id, 'generate_pdf')}>
                    PDF erstellen
                  </IonButton>
                )}
                {contract.status === 'draft' && contract.readiness && !contract.readiness.generation_allowed && (
                  <IonButton
                    size="small"
                    fill="outline"
                    disabled
                    title={(contract.readiness.blocking_issues || []).map((issue: any) => issue.label).join(' · ') || 'Dokument ist noch nicht erzeugbar.'}
                  >
                    PDF nicht bereit
                  </IonButton>
                )}`;
if (appNext.includes(legacyGenerateButton)) {
  appNext = appNext.replace(legacyGenerateButton, readinessGenerateButton);
} else if (!appNext.includes('PDF nicht bereit')) {
  throw new Error('Contract PDF action marker changed; update prepare-build.mjs.');
}

const legacySendCondition = `{['draft', 'ready'].includes(contract.status) && (`;
const readinessSendCondition = `{contract.readiness?.send_allowed && (`;
if (appNext.includes(legacySendCondition)) {
  appNext = appNext.replace(legacySendCondition, readinessSendCondition);
} else if (!appNext.includes(readinessSendCondition)) {
  throw new Error('Contract send action marker changed; update prepare-build.mjs.');
}

const legacySignatureCondition = `{(['client', 'worker'].includes(user.role) || isManager(user)) && ['ready', 'sent'].includes(contract.status) && !contract.signatures?.some((item: any) => item.role === (isManager(user) ? 'employer' : user.role === 'worker' ? 'employee' : 'client')) && (`;
const readinessSignatureCondition = `{(['client', 'worker'].includes(user.role) || isManager(user)) && ['ready', 'sent'].includes(contract.status) && contract.readiness?.pending_signature_roles?.includes(isManager(user) ? 'employer' : user.role === 'worker' ? 'employee' : 'client') && (`;
if (appNext.includes(legacySignatureCondition)) {
  appNext = appNext.replace(legacySignatureCondition, readinessSignatureCondition);
} else if (!appNext.includes(readinessSignatureCondition)) {
  throw new Error('Contract signature action marker changed; update prepare-build.mjs.');
}

// Clients need their own scoped locations when creating an order. Managers still
// receive the full master-data pair, while clients never load the global client list.
const managerOnlyOrderMasterData = `    if (isManager(user)) {
      const [clientData, locationData] = await Promise.all([api('clients/?ordering=name'), api('locations/')]);
      setClients(unpack(clientData).filter((client: any) => client.active));
      setLocations(unpack(locationData).filter((location: any) => location.active));
    }`;
const scopedOrderMasterData = `    if (isManager(user)) {
      const [clientData, locationData] = await Promise.all([api('clients/?ordering=name'), api('locations/')]);
      setClients(unpack(clientData).filter((client: any) => client.active));
      setLocations(unpack(locationData).filter((location: any) => location.active));
    } else if (user.role === 'client') {
      const locationData = await api('locations/');
      setLocations(unpack(locationData).filter((location: any) => location.active));
    }`;
if (appNext.includes(scopedOrderMasterData)) {
  // Already scoped in source; keep prepare:build idempotent.
} else if (appNext.includes(managerOnlyOrderMasterData)) {
  appNext = appNext.replace(managerOnlyOrderMasterData, scopedOrderMasterData);
} else {
  throw new Error('Client order location loading marker changed; update prepare-build.mjs.');
}

// Do not expose the broad worker directory to clients. Rating candidates are a
// minimal backend-curated list of workers actually assigned to completed shifts
// of this client, and already-rated assignments are removed server-side.
const legacyRatingLoad = `  const load = async () => {
    const [ratingData, workerData, shiftData] = await Promise.all([
      api('ratings/'),
      api('workers/'),
      api('shifts/'),
    ]);
    setRows(unpack(ratingData));
    setWorkers(unpack(workerData).filter((worker: any) => worker.active));
    setShifts(unpack(shiftData));
  };`;
const safeRatingLoad = `  const load = async () => {
    if (user.role === 'client') {
      const [ratingData, candidateData] = await Promise.all([
        api('ratings/'),
        api('portal/rating-candidates/'),
      ]);
      const candidates = unpack(candidateData);
      const workerMap = new Map<string, any>();
      const shiftMap = new Map<string, any>();
      candidates.forEach((candidate: any) => {
        const current = workerMap.get(candidate.worker_id) || {
          id: candidate.worker_id,
          active: true,
          user_detail: { name: candidate.worker_name },
          shift_ids: [],
        };
        if (!current.shift_ids.includes(candidate.shift_id)) current.shift_ids.push(candidate.shift_id);
        workerMap.set(candidate.worker_id, current);
        if (!shiftMap.has(candidate.shift_id)) {
          shiftMap.set(candidate.shift_id, {
            id: candidate.shift_id,
            position_name: candidate.position_name,
            location_name: candidate.location_name,
            starts_at: candidate.starts_at,
            ends_at: candidate.ends_at,
          });
        }
      });
      setRows(unpack(ratingData));
      setWorkers(Array.from(workerMap.values()));
      setShifts(Array.from(shiftMap.values()));
      return;
    }
    const [ratingData, workerData, shiftData] = await Promise.all([
      api('ratings/'),
      api('workers/'),
      api('shifts/'),
    ]);
    setRows(unpack(ratingData));
    setWorkers(unpack(workerData).filter((worker: any) => worker.active));
    setShifts(unpack(shiftData));
  };`;
if (appNext.includes(legacyRatingLoad)) {
  appNext = appNext.replace(legacyRatingLoad, safeRatingLoad);
} else if (!appNext.includes("api('portal/rating-candidates/')")) {
  throw new Error('Client rating loader marker changed; update prepare-build.mjs.');
}

const generalRatingOption = `          <IonSelectOption value="">Allgemeine Bewertung</IonSelectOption>`;
const requiredShiftOption = `          <IonSelectOption value="" disabled>Einsatz auswählen</IonSelectOption>`;
if (appNext.includes(generalRatingOption)) appNext = appNext.replace(generalRatingOption, requiredShiftOption);

const ratingShiftLabel = `          label="Einsatz"`;
if (appNext.includes(ratingShiftLabel)) appNext = appNext.replace(ratingShiftLabel, `          label="Einsatz *"`);

const ratingShiftChange = `          onIonChange={(event) => setForm({ ...form, shift: value(event) })}`;
const safeRatingShiftChange = `          onIonChange={(event) => setForm({ ...form, shift: value(event), worker: '' })}`;
if (appNext.includes(ratingShiftChange)) appNext = appNext.replace(ratingShiftChange, safeRatingShiftChange);

const allRatingWorkers = `          {workers.map((worker) => (`;
const scopedRatingWorkers = `          {workers.filter((worker) => !form.shift || worker.shift_ids?.includes(form.shift)).map((worker) => (`;
if (appNext.includes(allRatingWorkers)) {
  // The first matching map inside Ratings is the employee picker. Restrict only
  // that occurrence; manager document/payroll pickers remain untouched.
  const ratingsStart = appNext.indexOf('function Ratings({ user }');
  const workersMapIndex = appNext.indexOf(allRatingWorkers, ratingsStart);
  if (workersMapIndex >= 0) {
    appNext = appNext.slice(0, workersMapIndex) + scopedRatingWorkers + appNext.slice(workersMapIndex + allRatingWorkers.length);
  }
} else if (!appNext.includes('worker.shift_ids?.includes(form.shift)')) {
  throw new Error('Client rating worker picker marker changed; update prepare-build.mjs.');
}

// Client dashboard counters must use the privacy-safe endpoint so hidden client
// contracts are not leaked indirectly through the "Zu unterzeichnen" count.
const genericDashboardLoad = `  const load = () => api('dashboard/').then(setData);`;
const roleAwareDashboardLoad = `  const load = () => api(user.role === 'client' ? 'portal/client-dashboard/' : 'dashboard/').then(setData);`;
if (appNext.includes(genericDashboardLoad)) {
  appNext = appNext.replace(genericDashboardLoad, roleAwareDashboardLoad);
} else if (!appNext.includes("api(user.role === 'client' ? 'portal/client-dashboard/' : 'dashboard/')")) {
  throw new Error('Client dashboard loader marker changed; update prepare-build.mjs.');
}

if (appNext !== appSource) {
  writeFileSync(appPath, appNext);
}

// Make the real drawing signature pad deterministic in dev, production and the
// native store builds. The enhancer converts the legacy signature textarea to a
// touch/mouse canvas while keeping the API payload unchanged.
const mainPath = new URL('../src/main.tsx', import.meta.url);
const mainSource = readFileSync(mainPath, 'utf8');
let mainNext = mainSource;
const resilienceImport = "import { installOperationalFetchResilience } from './operationalFetchResilience';";
const signatureImport = "import { installSignaturePad } from './signaturePad';";
if (!mainNext.includes(signatureImport)) {
  if (!mainNext.includes(resilienceImport)) throw new Error('main.tsx resilience import marker changed; update prepare-build.mjs.');
  mainNext = mainNext.replace(resilienceImport, `${resilienceImport}\n${signatureImport}`);
}
const resilienceInstall = 'installOperationalFetchResilience();';
const signatureInstall = 'installSignaturePad();';
if (!mainNext.includes(signatureInstall)) {
  if (!mainNext.includes(resilienceInstall)) throw new Error('main.tsx install marker changed; update prepare-build.mjs.');
  mainNext = mainNext.replace(resilienceInstall, `${resilienceInstall}\n${signatureInstall}`);
}
if (mainNext !== mainSource) writeFileSync(mainPath, mainNext);

// Ionic's IonDatetime derives a narrow implicit year window when min/max are
// absent on some mobile builds. Give unrestricted business date fields an
// explicit 1900..2100 range so contracts can be dated beyond 2027.
const friendlyPath = new URL('../src/FriendlyDateTimePicker.tsx', import.meta.url);
const friendlySource = readFileSync(friendlyPath, 'utf8');
let friendlyNext = friendlySource;
const nativeBounds = `              min={target.min ? toIonDatetimeValue(target.kind, target.min) : undefined}
              max={target.max ? toIonDatetimeValue(target.kind, target.max) : undefined}`;
const wideBounds = `              min={target.min ? toIonDatetimeValue(target.kind, target.min) : target.kind === 'date' || target.kind === 'month' ? '1900-01-01' : target.kind === 'datetime-local' ? '1900-01-01T00:00' : undefined}
              max={target.max ? toIonDatetimeValue(target.kind, target.max) : target.kind === 'date' || target.kind === 'month' ? '2100-12-31' : target.kind === 'datetime-local' ? '2100-12-31T23:59' : undefined}`;
if (friendlyNext.includes(nativeBounds)) {
  friendlyNext = friendlyNext.replace(nativeBounds, wideBounds);
} else if (!friendlyNext.includes("'2100-12-31'")) {
  throw new Error('FriendlyDateTimePicker bounds marker changed; update prepare-build.mjs.');
}
if (friendlyNext !== friendlySource) writeFileSync(friendlyPath, friendlyNext);

// Chrome/Windows renders native date inputs using the device/browser locale even
// when the app language is German. Workforce Pro must always show TT.MM.JJJJ,
// while still keeping a real calendar picker and ISO YYYY-MM-DD API values.
const premiumPath = new URL('../src/PremiumOperations.tsx', import.meta.url);
const premiumSource = readFileSync(premiumPath, 'utf8');
let premiumNext = premiumSource;

const nativeDateControl = `function DateControl({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}) {
  return <label className="premium-field-control"><span>{label}</span><div className="premium-input-shell"><IonInput aria-label={label} type="date" value={value} onIonInput={event=>onChange(String(event.detail.value||''))}/></div></label>;
}`;

const germanDateControl = `const formatGermanDate = (iso: string) => {
  const match = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(iso || '');
  return match ? match[3] + '.' + match[2] + '.' + match[1] : '';
};
const parseGermanDate = (text: string) => {
  const match = /^(\\d{1,2})\\.(\\d{1,2})\\.(\\d{4})$/.exec(text.trim());
  if (!match) return '';
  const day = Number(match[1]); const month = Number(match[2]); const year = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return '';
  return String(year).padStart(4, '0') + '-' + String(month).padStart(2, '0') + '-' + String(day).padStart(2, '0');
};

function DateControl({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}) {
  const [draft, setDraft] = useState(formatGermanDate(value));
  useEffect(() => setDraft(formatGermanDate(value)), [value]);
  const commit = () => {
    const iso = parseGermanDate(draft);
    if (iso) { onChange(iso); setDraft(formatGermanDate(iso)); }
    else setDraft(formatGermanDate(value));
  };
  return <label className="premium-field-control"><span>{label}</span><div className="premium-input-shell premium-date-shell">
    <input className="premium-date-text" aria-label={label} inputMode="numeric" placeholder="TT.MM.JJJJ" value={draft} onChange={event=>setDraft(event.currentTarget.value)} onBlur={commit} onKeyDown={event=>{ if(event.key==='Enter'){ event.preventDefault(); commit(); } }}/>
    <button type="button" className="premium-date-button" aria-label={label + ': Kalender öffnen'} onClick={event=>{ const picker=event.currentTarget.parentElement?.querySelector<HTMLInputElement>('.premium-native-date'); if(picker?.showPicker) picker.showPicker(); else picker?.click(); }}>▦</button>
    <input className="premium-native-date" type="date" tabIndex={-1} aria-hidden="true" value={value} onChange={event=>{ const iso=event.currentTarget.value; if(iso){ onChange(iso); setDraft(formatGermanDate(iso)); } }}/>
  </div></label>;
}`;

if (premiumNext.includes(nativeDateControl)) {
  premiumNext = premiumNext.replace(nativeDateControl, germanDateControl);
} else if (!premiumNext.includes('premium-date-text')) {
  throw new Error('PremiumOperations DateControl marker changed; update prepare-build.mjs.');
}

if (premiumNext !== premiumSource) {
  writeFileSync(premiumPath, premiumNext);
}

const premiumCssPath = new URL('../src/premium-operations.css', import.meta.url);
const premiumCssSource = readFileSync(premiumCssPath, 'utf8');
const germanDateCssMarker = '/* German Workforce Pro date control */';
const germanDateCss = `\n${germanDateCssMarker}\n.premium-date-shell{position:relative;display:flex;align-items:center;gap:8px;padding:0 8px 0 0}.premium-date-text{width:100%;min-width:0;border:0;outline:0;background:transparent;color:var(--ion-text-color,#17233b);font:inherit;padding:12px 10px}.premium-date-text::placeholder{color:#8290a8}.premium-date-button{flex:0 0 36px;width:36px;height:36px;border:0;border-radius:10px;background:#eef4ff;color:#1d63e9;font-size:18px;cursor:pointer}.premium-date-button:hover{background:#e2ecff}.premium-native-date{position:absolute;right:8px;bottom:2px;width:1px;height:1px;opacity:0;pointer-events:none}.premium-date-text:focus{box-shadow:none}\n`;
if (!premiumCssSource.includes(germanDateCssMarker)) {
  writeFileSync(premiumCssPath, premiumCssSource + germanDateCss);
}

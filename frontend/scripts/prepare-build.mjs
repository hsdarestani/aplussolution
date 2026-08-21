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

if (appNext !== appSource) {
  writeFileSync(appPath, appNext);
}

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
  return match ? \\`\\${match[3]}.\\${match[2]}.\\${match[1]}\\` : '';
};
const parseGermanDate = (text: string) => {
  const match = /^(\\d{1,2})\\.(\\d{1,2})\\.(\\d{4})$/.exec(text.trim());
  if (!match) return '';
  const day = Number(match[1]); const month = Number(match[2]); const year = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return '';
  return \\`\\${String(year).padStart(4, '0')}-\\${String(month).padStart(2, '0')}-\\${String(day).padStart(2, '0')}\\`;
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
    <button type="button" className="premium-date-button" aria-label={\\`\\${label}: Kalender öffnen\\`} onClick={event=>{ const picker=event.currentTarget.parentElement?.querySelector<HTMLInputElement>('.premium-native-date'); if(picker?.showPicker) picker.showPicker(); else picker?.click(); }}>▦</button>
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

import fs from 'node:fs';
import path from 'node:path';

const sourceFile = path.resolve('src/WiwEmployeeScheduleMobile.tsx');
const cssFile = path.resolve('src/wiw-employee-schedule-mobile.css');
const helperFile = path.resolve('scripts/employee-admin-parity-helpers.txt');
const weekTemplateFile = path.resolve('scripts/employee-admin-parity-week.txt');
let source = fs.readFileSync(sourceFile, 'utf8');

const interactionMarker = 'EMPLOYEE_ADMIN_WEEK_INTERACTION_V2';
if (!source.includes(interactionMarker)) {
  const swipeRefMarker = "  const swipe = useRef<{ x: number; y: number } | undefined>(undefined);";
  if (!source.includes(swipeRefMarker)) throw new Error('Employee week interaction marker changed: swipe ref');
  source = source.replace(
    swipeRefMarker,
    `${swipeRefMarker}\n  const weekTrackRef = useRef<HTMLDivElement>(null);\n  const swipeFrame = useRef<number | undefined>(undefined);\n  const swipeTravel = useRef(0);`,
  );

  const claimMarker = '  async function claim(shift: any) {';
  if (!source.includes(claimMarker)) throw new Error('Employee week interaction marker changed: claim');
  const helpers = fs.readFileSync(helperFile, 'utf8').trimEnd();
  source = source.replace(claimMarker, `${helpers}\n\n${claimMarker}`);

  const oldWeekStrip = `        <button type="button" aria-label="Vorherige Woche" onClick={() => setAnchor(addDays(anchor, -7))}>‹</button>\n        {days.map((day) => <button type="button" key={day} className={\`${'${day === anchor ? \'active \' : \'\'}${day === berlinToday() ? \'today\' : \'\'}'}\`} onClick={() => setAnchor(day)}><small>{dayLabel(day).slice(0, 2)}</small><b>{keyDate(day).getUTCDate()}</b></button>)}\n        <button type="button" aria-label="Nächste Woche" onClick={() => setAnchor(addDays(anchor, 7))}>›</button>`;
  const newWeekStrip = `        <button type="button" aria-label="Vorherige Woche" onClick={() => animateEmployeeWeek(-7)}>‹</button>\n        {days.map((day) => <button type="button" key={day} className={\`${'${day === anchor ? \'active \' : \'\'}${day === berlinToday() ? \'today\' : \'\'}'}\`} onClick={() => scrollToEmployeeDay(day)}><small>{dayLabel(day).slice(0, 2)}</small><b>{keyDate(day).getUTCDate()}</b></button>)}\n        <button type="button" aria-label="Nächste Woche" onClick={() => animateEmployeeWeek(7)}>›</button>`;
  if (!source.includes(oldWeekStrip)) throw new Error('Employee week interaction marker changed: week strip');
  source = source.replace(oldWeekStrip, newWeekStrip);

  const bodyStartMarker = `\n      <div\n        className="wiw-week-scroll"`;
  const bodyEndMarker = `\n\n      {mode !== 'open' ? <div className="wiw-week-total"`;
  const bodyStart = source.indexOf(bodyStartMarker);
  const bodyEnd = source.indexOf(bodyEndMarker, bodyStart);
  if (bodyStart < 0 || bodyEnd < 0) throw new Error('Employee week interaction marker changed: week body');
  const weekTemplate = fs.readFileSync(weekTemplateFile, 'utf8').trim();
  source = `${source.slice(0, bodyStart)}\n      ${weekTemplate}${source.slice(bodyEnd)}`;

  source = `// ${interactionMarker}\n${source}`;
  fs.writeFileSync(sourceFile, source);
}

const requiredMarkers = [
  "api('employee/schedule/?ordering=starts_at')",
  "const [serviceSchedule, setServiceSchedule] = useState(false);",
  'data-testid="phase8-week-strip"',
  'data-testid="schedule-day-view"',
  'data-testid="phase8-week-total"',
  'visible.filter(isOwnShift)',
  'assignedNames(shift)',
  'Nur sichtbar · Service Zeitplan',
  'wiw-employee-admin-parity',
  'wiw-employee-week-swipe-track',
  'renderEmployeeMineWeek(addDays(weekStart, -7), true)',
  'renderEmployeeMineWeek(addDays(weekStart, 7), true)',
  'scrollToEmployeeDay(day)',
  'animateEmployeeWeek(7)',
];

const missing = requiredMarkers.filter((marker) => !source.includes(marker));
if (missing.length) {
  throw new Error(`Service Zeitplan calendar contract missing: ${missing.join(', ')}`);
}

const layoutMarker = '/* EMPLOYEE_ADMIN_PARITY_LAYOUT_FIX_V1 */';
const interactionCssMarker = '/* EMPLOYEE_ADMIN_WEEK_INTERACTION_V2 */';
let css = fs.readFileSync(cssFile, 'utf8');
if (!css.includes(layoutMarker)) {
  css += `\n\n${layoutMarker}\n@media (max-width:900px){\n  body.wiw-employee-schedule-active .app-main{\n    position:relative!important;\n    min-height:calc(100dvh - 126px)!important;\n    overflow:visible!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity{\n    position:relative!important;\n    inset:auto!important;\n    z-index:1!important;\n    display:block!important;\n    width:100%!important;\n    min-height:calc(100dvh - 128px)!important;\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-schedule-tools{\n    display:block!important;\n    position:sticky!important;\n    top:0!important;\n    z-index:12!important;\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-tabs{\n    display:flex!important;\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-week-strip{\n    display:grid!important;\n    position:sticky!important;\n    top:42px!important;\n    z-index:11!important;\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-week-scroll{\n    display:block!important;\n    position:relative!important;\n    z-index:1!important;\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-day-section,\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-shift-card{\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity.is-open-list .wiw-week-scroll{\n    padding-bottom:calc(78px + env(safe-area-inset-bottom))!important;\n  }\n}\n`;
}

if (!css.includes(interactionCssMarker)) {
  css += `\n\n${interactionCssMarker}\n@media (max-width:900px){\n  body.wiw-employee-schedule-active .wiw-employee-week-swipe-viewport{\n    width:100%;\n    overflow:clip;\n    clip-path:inset(0);\n    background:#f0f0f0;\n    overflow-anchor:none;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-week-swipe-track{\n    --wiw-employee-swipe-x:0px;\n    width:300%;\n    margin-left:-100%;\n    display:flex;\n    align-items:flex-start;\n    transform:translate3d(var(--wiw-employee-swipe-x),0,0);\n    will-change:transform;\n    touch-action:pan-y;\n    overscroll-behavior-x:contain;\n    overflow-anchor:none;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-week-swipe-track.is-dragging{\n    transition:none!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-week-swipe-track.is-settling{\n    transition:transform .18s ease-out;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-week-pane{\n    width:33.333333%;\n    flex:0 0 33.333333%;\n    min-width:0;\n    padding-bottom:calc(124px + env(safe-area-inset-bottom));\n    background:#f0f0f0;\n    overflow-anchor:none;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-week-preview{\n    pointer-events:none;\n    user-select:none;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-week-current .wiw-day-section{\n    scroll-margin-top:98px;\n  }\n}\n@supports not (overflow:clip){\n  @media (max-width:900px){\n    body.wiw-employee-schedule-active .wiw-employee-week-swipe-viewport{overflow:hidden;}\n  }\n}\n`;
}

fs.writeFileSync(cssFile, css);
console.log('Service Zeitplan admin parity, adjacent-week swipe and day navigation are integrated in source.');

import fs from 'node:fs';
import path from 'node:path';

const sourceFile = path.resolve('src/WiwEmployeeScheduleMobile.tsx');
const cssFile = path.resolve('src/wiw-employee-schedule-mobile.css');
const source = fs.readFileSync(sourceFile, 'utf8');

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
];

const missing = requiredMarkers.filter((marker) => !source.includes(marker));
if (missing.length) {
  throw new Error(`Service Zeitplan calendar contract missing: ${missing.join(', ')}`);
}

// The employee view intentionally reuses the admin schedule classes so both
// surfaces have exactly the same card/day/open-shift visuals. The admin root is
// absolutely positioned because the admin body activates wiw-native-schedule-active.
// Workers do not activate that body class, so reusing .wiw-schedule-mobile without
// this override can position the whole employee planner against the wrong ancestor:
// the fixed total remains visible while tabs/week/cards sit underneath the app shell.
// Keep the employee root in normal .app-main flow instead.
const layoutMarker = '/* EMPLOYEE_ADMIN_PARITY_LAYOUT_FIX_V1 */';
let css = fs.readFileSync(cssFile, 'utf8');
if (!css.includes(layoutMarker)) {
  css += `\n\n${layoutMarker}\n@media (max-width:900px){\n  body.wiw-employee-schedule-active .app-main{\n    position:relative!important;\n    min-height:calc(100dvh - 126px)!important;\n    overflow:visible!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity{\n    position:relative!important;\n    inset:auto!important;\n    z-index:1!important;\n    display:block!important;\n    width:100%!important;\n    min-height:calc(100dvh - 128px)!important;\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-schedule-tools{\n    display:block!important;\n    position:sticky!important;\n    top:0!important;\n    z-index:12!important;\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-tabs{\n    display:flex!important;\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-week-strip{\n    display:grid!important;\n    position:sticky!important;\n    top:42px!important;\n    z-index:11!important;\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-week-scroll{\n    display:block!important;\n    position:relative!important;\n    z-index:1!important;\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-day-section,\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity .wiw-shift-card{\n    visibility:visible!important;\n    opacity:1!important;\n  }\n  body.wiw-employee-schedule-active .wiw-employee-admin-parity.is-open-list .wiw-week-scroll{\n    padding-bottom:calc(78px + env(safe-area-inset-bottom))!important;\n  }\n}\n`;
  fs.writeFileSync(cssFile, css);
}

console.log('Service Zeitplan visibility, weekly calendar and employee/admin layout parity are integrated in source.');

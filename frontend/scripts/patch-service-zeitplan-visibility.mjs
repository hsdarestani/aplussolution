import fs from 'node:fs';
import path from 'node:path';

const file = path.resolve('src/WiwEmployeeScheduleMobile.tsx');
const source = fs.readFileSync(file, 'utf8');

const requiredMarkers = [
  "api('employee/schedule/?ordering=starts_at')",
  "const [serviceSchedule, setServiceSchedule] = useState(false);",
  'data-testid="phase8-week-strip"',
  'data-testid="schedule-day-view"',
  'data-testid="phase8-week-total"',
  'visible.filter(isOwnShift)',
  'assignedNames(shift)',
  'Nur sichtbar · Service Zeitplan',
];

const missing = requiredMarkers.filter((marker) => !source.includes(marker));
if (missing.length) {
  throw new Error(`Service Zeitplan calendar contract missing: ${missing.join(', ')}`);
}

console.log('Service Zeitplan visibility and weekly calendar are already integrated in source.');

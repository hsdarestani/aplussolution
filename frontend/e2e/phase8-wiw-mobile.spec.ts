import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Final Phase 8 acceptance contract for the production candidate.
const read=(path:string)=>readFileSync(resolve(process.cwd(),path),'utf8');

test('Phase 8 bottom navigation keeps Mitteilungen inside Mehr', async()=>{
  const app=read('src/App.tsx');
  expect(app).toContain("const primaryViews: View[] = ['dashboard', 'schedule', 'time'];");
  expect(app).toContain("dashboard: 'Dashboard'");
  expect(app).toContain("time: 'Zeiterfassung'");
  expect(app).not.toContain("['dashboard', 'schedule', 'time', 'messages']");
});

test('Phase 8 worker dashboard follows the WIW employee hierarchy and GPS clock flow', async()=>{
  const home=read('src/EmployeeHome.tsx');
  for(const label of ['Anfragen','Schichtanfragen','OpenShift-Anfragen','Mein Zeitplan','Meine Schichten','OpenShifts verfügbar','Zeiterfassung','Wichtige bevorstehende Daten','Einstempeln','Ausstempeln']){
    expect(home).toContain(label);
  }
  expect(home).toContain('Für die Zeiterfassung ist eine Berechtigung zur Standortbestimmung erforderlich');
  expect(home).toContain('Standortdienste aktivieren');
  expect(home).toContain("navigator.geolocation.getCurrentPosition");
  expect(home).toContain("api(`time-entries/clock_${clockIntent}/`");
});

test('Phase 8 attendance spans the complete imported history without removing clock mode', async()=>{
  const periods=read('src/Phase8MobileAttendance.tsx');
  const attendance=read('src/AttendanceV3.tsx');
  expect(periods).toContain('monthDistance');
  expect(periods).toContain('const earliest=');
  expect(periods).toContain('Array.from({length:count}');
  expect(periods).not.toContain('Array.from({length:13}');
  expect(periods).toContain('Abrechnungszeiträume');
  expect(periods).toContain('entry.worked_minutes');
  expect(attendance).toContain("api('attendance/history/')");
  expect(attendance).toContain('<Phase8MobileAttendance data={data} showWorker={isManager(user)} />');
});

test('Phase 8 worker scheduler exposes WIW week strip, names, totals and approved release requests', async()=>{
  const schedule=read('src/WiwEmployeeScheduleMobile.tsx');
  expect(schedule).toContain('phase8-week-strip');
  expect(schedule).toContain('phase8-week-total');
  expect(schedule).toContain('Gesamtstunden');
  expect(schedule).toContain('Meine Schichten');
  expect(schedule).toContain('OpenShifts');
  expect(schedule).toContain('Schicht übernommen. Dein Name steht jetzt im Dienstplan.');
  expect(schedule).toContain('Freigeben');
  expect(schedule).toContain('employee/shifts/${shift.id}/release-request/');
  expect(schedule).toContain('bis die Administration zustimmt');
});

test('Phase 8 admin scheduler keeps WIW week strip, total hours and mobile create control', async()=>{
  const schedule=read('src/ScheduleV2.tsx');
  expect(schedule).toContain("matchMedia('(max-width: 900px)').matches?'day':'list'");
  expect(schedule).toContain('phase8-week-strip');
  expect(schedule).toContain('phase8-week-total');
  expect(schedule).toContain('Gesamtstunden');
  expect(schedule).toContain('sv2-wiw-fab');
  expect(schedule).toContain('sv2-mini-actions');
});

test('Phase 8 mobile visual override is mobile-only and keeps A+ identity', async()=>{
  const css=read('src/phase8-wiw-mobile.css');
  expect(css).toContain('@media (max-width: 900px)');
  expect(css).toContain('--wiw-primary: #155eef');
  expect(css).toContain('grid-template-columns: repeat(4,minmax(0,1fr))');
  expect(css).toContain('.wiw-section-label');
  expect(css).toContain('.sv2-wiw-week-strip');
  expect(css).toContain('.sv2-mini-actions');
});


test('final Dienstplan UX keeps requested client order, hotel presets, copy label and edit reassignment', async () => {
  const adminSchedule = read('src/WiwScheduleMobile.tsx');
  const palette = read('src/scheduleClientPalette.ts');
  const css = read('src/wiw-schedule-mobile.css');
  expect(adminSchedule).toContain("'marthasfinest','stadthausammarkt','hotelspenerhaus','hofelcatering','restauranthirschgarten','messe','ommia','citybeach','hofgut'");
  expect(adminSchedule).toContain("label: 'Frühdienst', start: 6 * 60 + 30, end: 15 * 60");
  expect(adminSchedule).toContain("label: 'Spätdienst', start: 14 * 60 + 45, end: 22 * 60 + 45");
  expect(adminSchedule).toContain("label: 'Nachtdienst', start: 22 * 60 + 30, end: 24 * 60 + 6 * 60 + 30");
  expect(adminSchedule).toContain('Schicht kopieren');
  expect(adminSchedule).toContain("const uniqueLocation = matchingLocations.length === 1 ? String(matchingLocations[0].id) : ''");
  expect(adminSchedule).toContain("workerId: card.worker?.id ? String(card.worker.id) : ''");
  expect(adminSchedule).toContain('const workerChanged =');
  expect(css).toContain('.wiw-open-alert{margin-left:16px!important}');
  expect(css).toContain('.wiw-client-divider{height:3px;background:#111');
  expect(palette).toContain('fallbackHues');
});


test('WIW motion uses live quarter-hour ticks and strong swipe feedback', async()=>{
  const schedule=read('src/WiwScheduleMobile.tsx');
  const css=read('src/wiw-schedule-mobile.css');
  const employee=read('src/WiwEmployeeScheduleMobile.tsx');
  expect(schedule).toContain('window.requestAnimationFrame(emitTick)');
  expect(schedule).toContain("classList.add('is-swipe-dragging')");
  expect(css).toContain('scroll-snap-type:y mandatory');
  expect(css).toContain('scroll-snap-stop:always');
  expect(css).toContain('translate3d(24vw,0,0)');
  expect(employee).toContain('</div>, document.body) : null}');
});

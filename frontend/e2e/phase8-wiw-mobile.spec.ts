import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const read=(path:string)=>readFileSync(resolve(process.cwd(),path),'utf8');

test('Phase 8 bottom navigation keeps Mitteilungen inside Mehr', async()=>{
  const app=read('src/App.tsx');
  expect(app).toContain("const primaryViews: View[] = ['dashboard', 'schedule', 'time'];");
  expect(app).toContain("dashboard: 'Dashboard'");
  expect(app).toContain("time: 'Zeiterfassung'");
  expect(app).not.toContain("['dashboard', 'schedule', 'time', 'messages']");
});

test('Phase 8 worker dashboard follows the WIW section hierarchy', async()=>{
  const home=read('src/EmployeeHome.tsx');
  for(const label of ['Heute','Arbeitszeit-Hinweise','Mitarbeiteraktivität','Anfragen','Abwesenheitsanträge','Schichtanfragen','OpenShift-Anfragen','Mein Dienstplan','OpenShifts verfügbar','Wichtige anstehende Termine','Einstempeln']){
    expect(home).toContain(label);
  }
  expect(home).toContain("sessionStorage.setItem('phase8:attendance-clock','1')");
});

test('Phase 8 attendance exposes 13 pay periods on mobile without removing clock mode', async()=>{
  const periods=read('src/Phase8MobileAttendance.tsx');
  const attendance=read('src/AttendanceV3.tsx');
  expect(periods).toContain('Array.from({length:13}');
  expect(periods).toContain('Abrechnungszeiträume');
  expect(attendance).toContain("sessionStorage.getItem('phase8:attendance-clock') === '1'");
  expect(attendance).toContain('<Phase8MobileAttendance data={data} />');
});

test('Phase 8 scheduler exposes WIW week strip, total hours and mobile create control', async()=>{
  const schedule=read('src/ScheduleV2.tsx');
  expect(schedule).toContain("matchMedia('(max-width: 900px)').matches?'day':'list'");
  expect(schedule).toContain('phase8-week-strip');
  expect(schedule).toContain('phase8-week-total');
  expect(schedule).toContain('Gesamtstunden');
  expect(schedule).toContain('sv2-wiw-fab');
});

test('Phase 8 mobile visual override is mobile-only and keeps A+ identity', async()=>{
  const css=read('src/phase8-wiw-mobile.css');
  expect(css).toContain('@media (max-width: 900px)');
  expect(css).toContain('--wiw-primary: #155eef');
  expect(css).toContain('grid-template-columns: repeat(4,minmax(0,1fr))');
  expect(css).toContain('.wiw-section-label');
  expect(css).toContain('.sv2-wiw-week-strip');
});

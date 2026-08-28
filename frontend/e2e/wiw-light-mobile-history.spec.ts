import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const source = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');

test('all schedule views use icon plus value without customer legend noise', async () => {
  const css = source('src/wiw-mobile-light.css');
  const schedule = source('src/ScheduleV2.tsx');

  expect(css).toContain('.sv2-client-legend{display:none!important}');
  expect(css).toContain('.sv2-event-details .sv2-field-copy>small{display:none!important}');
  expect(schedule).toContain("view==='list'");
  expect(schedule).toContain("view==='day'");
  expect(schedule).toContain("view==='week'");
  expect(schedule).toContain("view==='month'");
  expect(schedule).toContain("view==='timeline'");
  expect(schedule).toContain('renderShiftDetails');
});

test('mobile defaults to light, keeps optional dark mode and uses a WIW-style More page', async () => {
  const css = source('src/wiw-mobile-light.css');
  const appearance = source('src/mobileAppearance.ts');
  const more = source('src/MobileMoreMenu.tsx');
  const app = source('src/App.tsx');
  const main = source('src/main.tsx');

  expect(css).toContain('--wiw-bg:#fff');
  expect(css).toContain("html[data-aplus-appearance='dark']");
  expect(appearance).toContain("return window.localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'");
  expect(main).toContain("import './wiw-mobile-light.css';");
  expect(main).toContain('installMobileAppearance();');
  expect(more).toContain('Profil & Einstellungen');
  expect(more).toContain('Darstellung');
  expect(more).toContain('Hell');
  expect(more).toContain('Dunkel');
  expect(more).not.toContain('WorkChat');
  expect(app).toContain("data-view={mobileMenuOpen ? 'more' : view}");
  expect(app).toContain('if (mobileMenuOpen)');
  expect(app).toContain('content = <MobileMoreMenu');
  expect(app).toContain('className={mobileMenuOpen || !primaryViews.includes(view)');
});

test('admin dashboard and attendance follow the supplied WIW mobile hierarchy', async () => {
  const admin = source('src/AdminHomeV4.tsx');
  const attendance = source('src/Phase8MobileAttendance.tsx');
  const attendanceShell = source('src/AttendanceV3.tsx');

  expect(admin).toContain('wiw-mobile-admin-dashboard');
  expect(admin).toContain('Arbeitszeit-Hinweise');
  expect(admin).toContain('Mitarbeiteraktivität');
  expect(admin).toContain('Abwesenheitsanträge');
  expect(admin).toContain('OpenShift-Anfragen');
  expect(admin).toContain('Wichtige anstehende Termine');

  expect(attendance).toContain('monthDistance');
  expect(attendance).toContain('const earliest=');
  expect(attendance).not.toContain('Array.from({length:13}');
  expect(attendanceShell).toContain("api('attendance/history/')");
  expect(attendanceShell).toContain('showWorker={isManager(user)}');
});

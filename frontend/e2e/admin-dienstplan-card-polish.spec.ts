import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const read = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');

test('admin Dienstplan stacks worker name and position beside a vertically centered avatar', async () => {
  const schedule = read('src/WiwScheduleMobile.tsx');
  const css = read('src/sep13-dienstplan-polish.css');

  expect(schedule).toContain('className="wiw-card-main"');
  expect(schedule).toContain('className="wiw-card-identity"');
  expect(schedule).toContain('<WorkerAvatar worker={card.worker} />');
  expect(schedule).toContain('{positionShortLabel(card.shift.position_name)}</small>');
  expect(css).toContain('.wiw-shift-card .wiw-card-main');
  expect(css).toContain('align-items:center');
  expect(css).toContain('.wiw-shift-card .wiw-card-identity');
  expect(css).toContain('flex-direction:column');
  expect(css).toContain('width:36px!important');
});

test('admin Dienstplan day label is larger and shows daily staff hours beside shift count', async () => {
  const schedule = read('src/WiwScheduleMobile.tsx');
  const css = read('src/sep13-dienstplan-polish.css');

  expect(schedule).toContain('const dayHours = dayCards.reduce');
  expect(schedule).toContain('className="wiw-day-summary"');
  expect(schedule).toContain('{formatScheduleHours(dayHours)} Std.');
  expect(schedule).toContain('function scheduleCardHours');
  expect(css).toContain('.wiw-day-heading>strong');
  expect(css).toContain('font-size:14px!important');
  expect(css).toContain('.wiw-day-summary>span');
});

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def write(path, content):
    (ROOT / path).write_text(content, encoding='utf-8')


def replace_once(path, old, new):
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected 1 match, got {count}: {old[:120]!r}')
    write(path, text.replace(old, new, 1))


# Unknown/custom clients must still receive distinct colors, not one fallback hue.
replace_once(
    'frontend/src/scheduleClientPalette.ts',
    "const defaultPalette = vividPalette(198);",
    "const fallbackHues = [8, 42, 88, 138, 184, 224, 270, 318];\nfunction fallbackPalette(key: string): SchedulePalette {\n  if (!key) return vividPalette(198);\n  let hash = 0;\n  for (let index = 0; index < key.length; index += 1) hash = ((hash * 31) + key.charCodeAt(index)) >>> 0;\n  return vividPalette(fallbackHues[hash % fallbackHues.length]);\n}"
)
replace_once(
    'frontend/src/scheduleClientPalette.ts',
    "  return defaultPalette;",
    "  return fallbackPalette(client);"
)

# Reassignment hardening: do not touch sibling assignments when only the shift
# fields were edited. Call /assign only when this exact card's employee changed.
replace_once(
    'frontend/src/WiwScheduleMobile.tsx',
    "type EditingCard = { shiftId: string; slotId: string; parentCount: number; workerName?: string; isOpen: boolean };",
    "type EditingCard = { shiftId: string; slotId: string; parentCount: number; workerName?: string; workerId?: string; isOpen: boolean };"
)
replace_once(
    'frontend/src/WiwScheduleMobile.tsx',
    "setEditing({ shiftId: String(card.shift.id), slotId: String(card.slot.id), parentCount: Number(card.shift.required_count || 1), workerName: card.worker?.name, isOpen: card.isOpen });",
    "setEditing({ shiftId: String(card.shift.id), slotId: String(card.slot.id), parentCount: Number(card.shift.required_count || 1), workerName: card.worker?.name, workerId: card.worker?.id ? String(card.worker.id) : '', isOpen: card.isOpen });"
)
replace_once(
    'frontend/src/WiwScheduleMobile.tsx',
    """        const targetShiftId = String(edited?.shift?.id || editing.shiftId);
        await api(`shifts/${targetShiftId}/assign/`, {
          method: 'POST',
          body: JSON.stringify({ workers: form.workers.slice(0, 1), publish_remaining: form.publish_now }),
        });
        setToast(form.workers.length ? 'Schicht gespeichert · Mitarbeiterzuweisung aktualisiert.' : 'Schicht gespeichert · als OpenShift freigegeben.');""",
    """        const targetShiftId = String(edited?.shift?.id || editing.shiftId);
        const nextWorkerId = String(form.workers[0] || '');
        const workerChanged = String(editing.workerId || '') !== nextWorkerId;
        if (workerChanged) {
          await api(`shifts/${targetShiftId}/assign/`, {
            method: 'POST',
            body: JSON.stringify({ workers: nextWorkerId ? [nextWorkerId] : [], publish_remaining: form.publish_now }),
          });
        }
        setToast(workerChanged
          ? (nextWorkerId ? 'Schicht gespeichert · Mitarbeiter geändert.' : 'Schicht gespeichert · als OpenShift freigegeben.')
          : (form.apply_all ? 'Änderungen auf alle Karten angewendet.' : 'Schicht gespeichert.'));"""
)

# Update stale release-flow E2E expectations to the current employee chooser.
replace_once(
    'frontend/e2e/app-shell.spec.ts',
    """    await page.getByRole('button', { name: 'Freigeben' }).click();
    const releaseAlert = page.locator('ion-alert').filter({ hasText: 'Schicht freigeben?' }).last();
    await expect(releaseAlert).toBeVisible();
    await releaseAlert.getByRole('button', { name: 'Abbrechen' }).click();
    await expect(releaseAlert).toBeHidden();""",
    """    await page.getByRole('button', { name: 'Freigeben' }).click();
    const releaseSheet = page.getByRole('dialog', { name: 'Schicht freigeben' });
    await expect(releaseSheet).toBeVisible();
    await releaseSheet.getByRole('button', { name: 'Abbrechen' }).click();
    await expect(releaseSheet).toBeHidden();"""
)
replace_once(
    'frontend/e2e/worker-portal-deep.spec.ts',
    """    await page.getByRole('button', { name: 'Freigeben' }).click();
    await page.locator('ion-alert').getByRole('button', { name: 'Freigeben' }).click();
    await expect.poll(() => state.releaseRequested).toBe(true);""",
    """    await page.getByRole('button', { name: 'Freigeben' }).click();
    const releaseSheet = page.getByRole('dialog', { name: 'Schicht freigeben' });
    await expect(releaseSheet).toBeVisible();
    await releaseSheet.getByRole('button', { name: 'Freigabe anfragen' }).click();
    await expect.poll(() => state.releaseRequested).toBe(true);"""
)

# Mobile admin planning is the native WIW surface now; assert the real visible
# week strip/day groups instead of the intentionally hidden legacy ScheduleV2.
replace_once(
    'frontend/e2e/berlin-schedule.spec.ts',
    """test('mobile planning defaults to the vertically scrollable full week and keeps the week strip inside the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await page.clock.setFixedTime(fixedNow); await mockAdmin(page); await page.goto('/?view=schedule');
  await expect(page.getByTestId('phase8-week-strip')).toBeVisible();
  const week = page.getByTestId('schedule-week-view');
  await expect(week).toBeVisible();
  await expect(week.locator('.sv2-week-day')).toHaveCount(7);
  await expect(page.getByTestId('schedule-day-view')).toHaveCount(0);
  await expect(page.getByTestId('schedule-view-toolbar')).toBeHidden();
  await expect(page.locator('.sv2 > ion-segment ion-segment-button[value=\"all\"]')).toHaveClass(/segment-button-checked/);
  const noPageOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  expect(noPageOverflow).toBeTruthy();
});""",
    """test('mobile planning defaults to the vertically scrollable full week and keeps the week strip inside the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await page.clock.setFixedTime(fixedNow); await mockAdmin(page); await page.goto('/?view=schedule');
  const native = page.getByTestId('wiw-native-schedule');
  await expect(native).toBeVisible();
  await expect(native.locator('.wiw-week-strip')).toBeVisible();
  await expect(native.locator('.wiw-day-section')).toHaveCount(7);
  await expect(native.locator('.wiw-week-total')).toBeVisible();
  await expect(native.getByRole('tab', { name: 'Alle' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('schedule-view-toolbar')).toBeHidden();
  const noPageOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  expect(noPageOverflow).toBeTruthy();
});"""
)

# Friendly datetime mobile regression now follows the real WIW time wheel. It
# checks 15-minute increments and the six-hour default without relying on the
# hidden desktop/tablet form.
friendly = r'''import { expect, Page, Route, test } from '@playwright/test';

async function fulfill(route: Route, body: unknown, status = 200) { await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) }); }
async function mockAdmin(page: Page) {
  await page.addInitScript(() => { localStorage.setItem('access','friendly-datetime-access'); localStorage.setItem('refresh','friendly-datetime-refresh'); });
  await page.route('**/api/**', async route => {
    const path=new URL(route.request().url()).pathname.replace(/^\/api\//,'');
    if(path==='auth/me/') return fulfill(route,{id:'admin-1',email:'admin@example.test',name:'A+ Admin',first_name:'A+',last_name:'Admin',role:'admin',phone:''});
    if(path.startsWith('shifts/')) return fulfill(route,[]);
    if(path.startsWith('clients/')) return fulfill(route,[{id:'client-1',name:'Hotel Spenerhaus',active:true}]);
    if(path.startsWith('locations/')) return fulfill(route,[{id:'location-1',client:'client-1',name:'Hotel Spenerhaus',address:'Frankfurt',active:true}]);
    if(path.startsWith('positions/')) return fulfill(route,[{id:'position-1',name:'Front Office',active:true},{id:'position-2',name:'Housekeeping',active:true},{id:'position-3',name:'Servicekraft',active:true}]);
    if(path.startsWith('workers/')) return fulfill(route,[]);
    if(path==='admin/mobile-dashboard/') return fulfill(route,{open_shift_rows:[]});
    return fulfill(route,[]);
  });
}

const minute = (label: string) => {
  const clean = label.replace('~','').trim();
  const [hour, minute] = clean.split(':').map(Number);
  return hour * 60 + minute;
};

test('mobile shift form uses a 15-minute wheel and defaults the end six hours after start', async ({page}) => {
  await page.setViewportSize({width:390,height:844}); await mockAdmin(page); await page.goto('/?view=schedule');
  await expect(page.getByTestId('wiw-native-schedule')).toBeVisible();
  await page.locator('.wiw-create-fab').evaluate((element: HTMLButtonElement) => element.click());
  const createMenu = page.getByRole('dialog', { name: 'Schicht erstellen' });
  await expect(createMenu).toBeVisible();
  await createMenu.getByRole('button', { name: /Manuell/ }).click();

  const form = page.getByTestId('wiw-shift-form');
  await expect(form).toBeVisible();
  await form.getByRole('button', { name: /Wähle Zeitrahmen/ }).click();
  const wheel = page.getByTestId('wiw-time-wheel');
  await expect(wheel).toBeVisible();
  const columns = wheel.locator('.wiw-wheel-column');
  await expect(columns).toHaveCount(2);
  const labels = await columns.nth(0).locator('button').evaluateAll((buttons) => buttons.slice(0,3).map((button) => (button.textContent || '').trim()));
  expect(labels).toEqual(['00:00','00:15','00:30']);
  const startLabel = (await columns.nth(0).locator('button.active').textContent()) || '';
  const endLabel = (await columns.nth(1).locator('button.active').textContent()) || '';
  const diff = (minute(endLabel) - minute(startLabel) + 1440) % 1440;
  expect(diff).toBe(360);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth); expect(overflow).toBeLessThanOrEqual(1);
});
'''
write('frontend/e2e/friendly-datetime.spec.ts', friendly)

# Lock the requested final mobile UX contract in source-level E2E checks.
phase8 = read('frontend/e2e/phase8-wiw-mobile.spec.ts')
append = r'''

test('final Dienstplan UX keeps requested client order, hotel presets, copy label and edit reassignment', async () => {
  const adminSchedule = source('src/WiwScheduleMobile.tsx');
  const palette = source('src/scheduleClientPalette.ts');
  const css = source('src/wiw-schedule-mobile.css');
  expect(adminSchedule).toContain("'marthasfinest','stadthausammarkt','hotelspenerhaus','hofelcatering','restauranthirschgarten','messe','ommia','citybeach','hofgut'");
  expect(adminSchedule).toContain("label: 'Frühdienst', start: 6 * 60 + 30, end: 15 * 60");
  expect(adminSchedule).toContain("label: 'Spätdienst', start: 14 * 60 + 45, end: 22 * 60 + 45");
  expect(adminSchedule).toContain("label: 'Nachtdienst', start: 22 * 60 + 30, end: 24 * 60 + 6 * 60 + 30");
  expect(adminSchedule).toContain('Schicht kopieren');
  expect(adminSchedule).toContain("const serviceOnly = groups.length === 1 && groups[0] === 'service'");
  expect(adminSchedule).toContain("const uniqueLocation = matchingLocations.length === 1 ? String(matchingLocations[0].id) : ''");
  expect(adminSchedule).toContain("workerId: card.worker?.id ? String(card.worker.id) : ''");
  expect(adminSchedule).toContain('const workerChanged =');
  expect(css).toContain('.wiw-open-alert{margin-left:16px!important}');
  expect(css).toContain('.wiw-client-divider{height:3px;background:#111');
  expect(palette).toContain('fallbackHues');
});
'''
if 'final Dienstplan UX keeps requested client order' not in phase8:
    write('frontend/e2e/phase8-wiw-mobile.spec.ts', phase8 + append)

# Backend regression: an admin can replace a worker after shift creation and the
# new direct assignment is confirmed without another employee confirmation.
backend = read('backend/tests/test_admin_schedule_management.py')
backend_append = r'''

@pytest.mark.django_db
def test_admin_can_replace_worker_after_shift_creation_without_confirmation(
    auth_admin, company, location, position, worker_user, second_worker
):
    starts = timezone.now() + timedelta(days=14)
    created = auth_admin.post('/api/shifts/', {
        'client': str(company.id),
        'location': str(location.id),
        'position': str(position.id),
        'starts_at': starts.isoformat(),
        'ends_at': (starts + timedelta(hours=5)).isoformat(),
        'required_count': 1,
        'status': 'published',
        'confirmation_required': True,
    }, format='json')
    assert created.status_code == 201, created.data
    first = auth_admin.post(f"/api/shifts/{created.data['id']}/assign/", {
        'workers': [str(worker_user.worker_profile.id)],
        'publish_remaining': True,
    }, format='json')
    assert first.status_code == 200, first.data

    replaced = auth_admin.post(f"/api/shifts/{created.data['id']}/assign/", {
        'workers': [str(second_worker.id)],
        'publish_remaining': True,
    }, format='json')
    assert replaced.status_code == 200, replaced.data

    shift = Shift.objects.get(pk=created.data['id'])
    claimed = ShiftSlot.objects.get(shift=shift, status=ShiftSlot.Status.CLAIMED)
    assert claimed.worker_id == second_worker.id
    assert claimed.confirmation_status == ShiftSlot.ConfirmationStatus.CONFIRMED
    assert not ShiftSlot.objects.filter(shift=shift, worker=worker_user.worker_profile, status=ShiftSlot.Status.CLAIMED).exists()
'''
if 'test_admin_can_replace_worker_after_shift_creation_without_confirmation' not in backend:
    write('backend/tests/test_admin_schedule_management.py', backend + backend_append)

print('final_schedule_ux_followup: OK')

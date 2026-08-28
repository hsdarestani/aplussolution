from pathlib import Path


def replace_once(path: str, old: str, new: str):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'missing marker in {path}: {old[:120]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# Product fix: never let the archive overwrite the just-finished native clock entry.
replace_once(
    'frontend/src/AttendanceV3.tsx',
    "    const [main, timeOff, archive] = await Promise.all(requests);\n    setData(archive ? { ...main, history: archive.history || [], history_count: archive.count || 0 } : main);\n    setAbsences(unpack(timeOff));\n",
    "    const [main, timeOff, archive] = await Promise.all(requests);\n    if (archive) {\n      const archiveHistory = Array.isArray(archive?.history) ? archive.history : [];\n      const mainHistory = Array.isArray(main?.history) ? main.history : [];\n      const merged = new Map<string, any>();\n      // Archive first, then the live attendance/home response so a freshly\n      // clocked-out native row wins over any stale copy from the archive call.\n      [...archiveHistory, ...mainHistory].forEach((entry: any) => {\n        if (entry?.id) merged.set(String(entry.id), entry);\n      });\n      const history = Array.from(merged.values()).sort((a: any, b: any) =>\n        new Date(b.clock_in).getTime() - new Date(a.clock_in).getTime(),\n      );\n      setData({ ...main, history, history_count: archive.count ?? history.length });\n    } else {\n      setData(main);\n    }\n    setAbsences(unpack(timeOff));\n",
)

# Pay-period totals use the backend's worked_minutes (which already subtracts the shift pause).
replace_once(
    'frontend/src/Phase8MobileAttendance.tsx',
    "  const minutes=entries.reduce((sum:number,entry:any)=>{\n    if(!entry.clock_in||!entry.clock_out)return sum;\n    return sum+Math.max(0,Math.round((new Date(entry.clock_out).getTime()-new Date(entry.clock_in).getTime())/60000)-Number(entry.break_minutes||0));\n  },0);\n",
    "  const minutes=entries.reduce((sum:number,entry:any)=>{\n    if(Number.isFinite(Number(entry.worked_minutes))) return sum+Math.max(0,Number(entry.worked_minutes));\n    if(!entry.clock_in||!entry.clock_out)return sum;\n    return sum+Math.max(0,Math.round((new Date(entry.clock_out).getTime()-new Date(entry.clock_in).getTime())/60000));\n  },0);\n",
)

# Admin priority regression: desktop keeps the five quick actions; mobile intentionally uses WIW rows.
p = Path('frontend/e2e/admin-priority-navigation.spec.ts')
p.write_text("""import { expect, test } from '@playwright/test';

const admin = {
  id: 'admin-priority-user',
  email: 'admin@example.test',
  name: 'Alex Admin',
  first_name: 'Alex',
  last_name: 'Admin',
  role: 'admin',
  phone: '',
};

async function openAdminHome(page: any, width: number, height: number) {
  await page.setViewportSize({ width, height });
  await page.addInitScript(() => {
    localStorage.setItem('access', 'priority-e2e-access');
    localStorage.setItem('refresh', 'priority-e2e-refresh');
  });
  await page.route('**/api/**', async (route: any) => {
    const path = new URL(route.request().url()).pathname.replace(/^\\/api\\//, '');
    const body = path === 'auth/me/'
      ? admin
      : path.startsWith('admin/exceptions/')
        ? { summary: { critical: 0, warning: 0, by_category: {} }, results: [] }
        : [];
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/');
}

test('admin start uses WIW hierarchy on mobile and keeps desktop priority shortcuts', async ({ page }) => {
  await openAdminHome(page, 390, 844);
  const wiw = page.getByTestId('wiw-mobile-admin-dashboard');
  await expect(wiw).toBeVisible();
  for (const label of ['Arbeitszeit-Hinweise', 'Mitarbeiteraktivität', 'Abwesenheitsanträge', 'Schichtanfragen', 'OpenShift-Anfragen', 'Schichten', 'OpenShifts verfügbar']) {
    await expect(wiw.getByRole('button', { name: label, exact: true })).toBeVisible();
  }
  await expect(page.getByTestId('admin-priority-actions')).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  await openAdminHome(page, 1440, 1000);
  const priorities = page.getByTestId('admin-priority-actions');
  await expect(priorities).toBeVisible();
  await expect(priorities.getByRole('button')).toHaveCount(5);
  for (const label of ['Dienstplan', 'Zeiterfassung', 'Lohn & Anfragen', 'Personal & Kunden', 'Mitteilungen']) {
    await expect(priorities.getByRole('button', { name: label, exact: true })).toBeAttached();
  }
});
""", encoding='utf-8')

# Phase 8 acceptance evolves from fixed 13-month mock data to the real imported-history range.
p = Path('frontend/e2e/phase8-wiw-mobile.spec.ts')
text = p.read_text(encoding='utf-8')
old = """test('Phase 8 attendance exposes 13 pay periods on mobile without removing clock mode', async()=>{\n  const periods=read('src/Phase8MobileAttendance.tsx');\n  const attendance=read('src/AttendanceV3.tsx');\n  expect(periods).toContain('Array.from({length:13}');\n  expect(periods).toContain('Abrechnungszeiträume');\n  expect(attendance).toContain(\"sessionStorage.getItem('phase8:attendance-clock') === '1'\");\n  expect(attendance).toContain('<Phase8MobileAttendance data={data} />');\n});\n"""
new = """test('Phase 8 attendance spans the complete imported history without removing clock mode', async()=>{\n  const periods=read('src/Phase8MobileAttendance.tsx');\n  const attendance=read('src/AttendanceV3.tsx');\n  expect(periods).toContain('monthDistance');\n  expect(periods).toContain('const earliest=');\n  expect(periods).toContain('Array.from({length:count}');\n  expect(periods).not.toContain('Array.from({length:13}');\n  expect(periods).toContain('Abrechnungszeiträume');\n  expect(periods).toContain('entry.worked_minutes');\n  expect(attendance).toContain(\"sessionStorage.getItem('phase8:attendance-clock') === '1'\");\n  expect(attendance).toContain(\"api('attendance/history/')\");\n  expect(attendance).toContain('<Phase8MobileAttendance data={data} showWorker={isManager(user)} />');\n});\n"""
if old not in text:
    raise SystemExit('missing old Phase 8 attendance contract')
p.write_text(text.replace(old, new, 1), encoding='utf-8')

# App shell mobile tests now assert the true WIW More page and WIW admin mobile dashboard.
p = Path('frontend/e2e/app-shell.spec.ts')
text = p.read_text(encoding='utf-8')
replace_blocks = [
("""    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();\n    await expect(page.getByRole('heading', { name: 'Weitere Bereiche' })).toBeVisible();\n    const moreMenu = page.locator('.mobile-menu-grid');\n    await expect(moreMenu.getByRole('button', { name: 'Meine Verträge', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Dokumente', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Ranking', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Mitteilungen', exact: true })).toBeVisible();\n""",
"""    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();\n    const moreMenu = page.getByTestId('wiw-more-screen');\n    await expect(moreMenu).toBeVisible();\n    await expect(moreMenu.getByText('Mehr', { exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Meine Verträge', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Dokumente', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Ranking', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Mitteilungen', exact: true })).toBeVisible();\n"""),
("""    await expect(page.getByTestId('admin-exception-center')).toBeVisible();\n    await expect(page.getByRole('heading', { name: 'Nur das, was heute Aufmerksamkeit braucht.' })).toBeVisible();\n    await expect(page.getByText('Schicht noch nicht vollständig besetzt')).toBeVisible();\n    await expect(page.locator('.mobile-tabbar button')).toHaveCount(4);\n    await expectNoHorizontalPageOverflow(page);\n\n    await page.locator('.mobile-tabbar button').filter({ hasText: 'Zeiterfassung' }).click();\n    await expect(page.getByRole('heading', { name: /Ungewöhnlich lange (laufende Timer|offene Zeiterfassungen)/ })).toBeVisible();\n    await page.getByRole('button', { name: /Timer beenden|Prüfen & schließen/ }).click();\n    const closeAlert = page.locator('ion-alert');\n    await expect(closeAlert).toBeVisible();\n    await expect(closeAlert.locator('textarea')).toBeVisible();\n    await closeAlert.locator('textarea').fill('E2E Prüfung');\n    await page.getByRole('button', { name: 'Abbrechen' }).click();\n    await expect(closeAlert).toBeHidden();\n\n    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();\n    const moreMenu = page.locator('.mobile-menu-grid');\n    await expect(moreMenu.getByRole('button', { name: 'Verträge & ANÜ', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Lohn & Dokumente', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Anfragen, Berichte & Verwaltung', exact: true })).toBeVisible();\n""",
"""    await expect(page.getByTestId('admin-exception-center')).toBeVisible();\n    const dashboard = page.getByTestId('wiw-mobile-admin-dashboard');\n    await expect(dashboard).toBeVisible();\n    await expect(dashboard.getByRole('button', { name: 'Arbeitszeit-Hinweise', exact: true })).toBeVisible();\n    await expect(dashboard.getByRole('button', { name: 'Mitarbeiteraktivität', exact: true })).toBeVisible();\n    await expect(page.locator('.mobile-tabbar button')).toHaveCount(4);\n    await expectNoHorizontalPageOverflow(page);\n\n    await page.locator('.mobile-tabbar button').filter({ hasText: 'Zeiterfassung' }).click();\n    await expect(page.getByTestId('phase8-pay-periods')).toBeVisible();\n    await expect(page.getByText('Abrechnungszeiträume', { exact: true })).toBeVisible();\n\n    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();\n    const moreMenu = page.getByTestId('wiw-more-screen');\n    await expect(moreMenu.getByRole('button', { name: 'Verträge & ANÜ', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Lohn & Dokumente', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Anfragen, Berichte & Verwaltung', exact: true })).toBeVisible();\n"""),
("""    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();\n    const moreMenu = page.locator('.mobile-menu-grid');\n    await expect(moreMenu.getByRole('button', { name: 'Servicecenter', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Aufträge', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Verträge & Signatur', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Mitarbeiter bewerten', exact: true })).toBeVisible();\n""",
"""    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();\n    const moreMenu = page.getByTestId('wiw-more-screen');\n    await expect(moreMenu).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Servicecenter', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Aufträge', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Verträge & Signatur', exact: true })).toBeVisible();\n    await expect(moreMenu.getByRole('button', { name: 'Mitarbeiter bewerten', exact: true })).toBeVisible();\n"""),
]
for old, new in replace_blocks:
    if old not in text:
        raise SystemExit(f'missing app-shell block: {old[:80]!r}')
    text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

# Client deep mobile contract uses the new WIW More page.
replace_once(
    'frontend/e2e/client-portal-deep.spec.ts',
    """    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();\n    await expect(page.getByRole('heading', { name: 'Weitere Bereiche' })).toBeVisible();\n    await expect(page.getByRole('button', { name: /Verträge & Signatur/ })).toBeVisible();\n    await expect(page.getByRole('button', { name: /Dokumente/ })).toBeVisible();\n    await expect(page.getByRole('button', { name: /Mitarbeiter bewerten/ })).toBeVisible();\n""",
    """    await page.getByRole('button', { name: 'Weitere Bereiche öffnen' }).click();\n    const more = page.getByTestId('wiw-more-screen');\n    await expect(more).toBeVisible();\n    await expect(more.getByRole('button', { name: /Verträge & Signatur/ })).toBeVisible();\n    await expect(more.getByRole('button', { name: /Dokumente/ })).toBeVisible();\n    await expect(more.getByRole('button', { name: /Mitarbeiter bewerten/ })).toBeVisible();\n""",
)

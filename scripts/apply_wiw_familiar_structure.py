from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1))


# 1) Reorder information architecture around the familiar When I Work mental model:
# Dashboard -> Scheduler -> Attendance -> Payroll/Documents -> WorkChat -> Requests/Reports -> Workplace.
app = "frontend/src/App.tsx"
old_nav = """const nav: Record<string, [View, string][]> = {
  admin: [
    ['dashboard', 'Übersicht'],
    ['orders', 'Auftragseingang & AI'],
    ['schedule', 'Dienstplanung'],
    ['time', 'Zeiterfassung'],
    ['people', 'Personal & Kunden'],
    ['contracts', 'Verträge & ANÜ'],
    ['documents', 'Dokumente & Lohn'],
    ['messages', 'Nachrichten'],
    ['operations', 'Mehr / Steuerzentrale'],
  ],
  manager: [
    ['dashboard', 'Übersicht'],
    ['orders', 'Auftragseingang & AI'],
    ['schedule', 'Dienstplanung'],
    ['time', 'Zeiterfassung'],
    ['people', 'Personal & Kunden'],
    ['contracts', 'Verträge & ANÜ'],
    ['documents', 'Dokumente & Lohn'],
    ['messages', 'Nachrichten'],
    ['operations', 'Mehr / Steuerzentrale'],
  ],
  worker: [
    ['dashboard', 'Start'],
    ['schedule', 'Mein Dienstplan'],
    ['time', 'Arbeitszeitkonto'],
    ['operations', 'Verfügbarkeit & Tausch'],
    ['contracts', 'Meine Verträge'],
    ['documents', 'Dokumente & Lohn'],
    ['messages', 'Nachrichten'],
    ['ranking', 'Ranking'],
  ],
  client: [
    ['dashboard', 'Start'],
    ['operations', 'Servicecenter'],
    ['orders', 'Aufträge'],
    ['schedule', 'Einsätze'],
    ['contracts', 'Verträge & Signatur'],
    ['documents', 'Dokumente'],
    ['ratings', 'Mitarbeiter bewerten'],
    ['messages', 'Nachrichten'],
  ],
};"""
new_nav = """const nav: Record<string, [View, string][]> = {
  // Familiar workflow order inspired by the structure Ashkan and the team already know:
  // Übersicht -> Dienstplan -> Zeiterfassung -> Lohn/Dokumente -> Chat -> Anfragen -> Stammdaten.
  // A+ specific modules remain available afterwards instead of changing the learned daily workflow.
  admin: [
    ['dashboard', 'Übersicht'],
    ['schedule', 'Dienstplan'],
    ['time', 'Zeiterfassung'],
    ['documents', 'Lohn & Dokumente'],
    ['messages', 'Nachrichten'],
    ['operations', 'Anfragen, Berichte & Verwaltung'],
    ['people', 'Personal & Kunden'],
    ['orders', 'Aufträge & AI'],
    ['contracts', 'Verträge & ANÜ'],
  ],
  manager: [
    ['dashboard', 'Übersicht'],
    ['schedule', 'Dienstplan'],
    ['time', 'Zeiterfassung'],
    ['documents', 'Lohn & Dokumente'],
    ['messages', 'Nachrichten'],
    ['operations', 'Anfragen, Berichte & Verwaltung'],
    ['people', 'Personal & Kunden'],
    ['orders', 'Aufträge & AI'],
    ['contracts', 'Verträge & ANÜ'],
  ],
  worker: [
    ['dashboard', 'Start'],
    ['schedule', 'Mein Dienstplan'],
    ['time', 'Zeiterfassung'],
    ['messages', 'Nachrichten'],
    ['operations', 'Anfragen'],
    ['documents', 'Dokumente'],
    ['contracts', 'Meine Verträge'],
    ['ranking', 'Ranking'],
  ],
  client: [
    ['dashboard', 'Start'],
    ['operations', 'Servicecenter'],
    ['orders', 'Aufträge'],
    ['schedule', 'Einsätze'],
    ['contracts', 'Verträge & Signatur'],
    ['documents', 'Dokumente'],
    ['ratings', 'Mitarbeiter bewerten'],
    ['messages', 'Nachrichten'],
  ],
};"""
replace(app, old_nav, new_nav)

old_primary = """  const primaryViews: View[] = isManager(user)
    ? ['orders', 'schedule', 'time', 'people']
    : ['dashboard', 'schedule', 'time', 'messages'];"""
new_primary = """  const primaryViews: View[] = isManager(user)
    ? ['dashboard', 'schedule', 'time', 'messages']
    : ['dashboard', 'schedule', 'time', 'messages'];"""
replace(app, old_primary, new_primary)

# Keep short mobile labels, but make the schedule label explicit and familiar.
replace(app, "    schedule: 'Plan',", "    schedule: 'Dienstplan',")

# 2) Admin dashboard quick actions follow the same daily order.
home = "frontend/src/AdminHomeV4.tsx"
old_actions = """const priorityActions = [
  { view: 'orders', label: 'Auftrag & AI', hint: 'Anfrage einlesen', icon: briefcaseOutline },
  { view: 'schedule', label: 'Dienstplanung', hint: 'OpenShifts & Besetzung', icon: calendarOutline },
  { view: 'time', label: 'Zeiterfassung', hint: 'Zeiten prüfen', icon: timeOutline },
  { view: 'operations', label: 'Arbeitszeit & Lohn', hint: 'Saldo & Vorbereitung', icon: walletOutline },
  { view: 'people', label: 'Personal & Kunden', hint: 'Stammdaten & Zugänge', icon: peopleOutline },
];"""
new_actions = """const priorityActions = [
  { view: 'schedule', label: 'Dienstplan', hint: 'OpenShifts & Besetzung', icon: calendarOutline },
  { view: 'time', label: 'Zeiterfassung', hint: 'Zeiten prüfen', icon: timeOutline },
  { view: 'operations', label: 'Lohn & Anfragen', hint: 'Freigaben, Saldo & Berichte', icon: walletOutline },
  { view: 'people', label: 'Personal & Kunden', hint: 'Stammdaten & Zugänge', icon: peopleOutline },
  { view: 'orders', label: 'Aufträge & AI', hint: 'Anfragen einlesen', icon: briefcaseOutline },
];"""
replace(home, old_actions, new_actions)

# 3) Role-specific request/administration page names align with the navigation.
operations = "frontend/src/Operations.tsx"
old_title = """  const pageTitle = isManager(user)
    ? 'Steuerzentrale'
    : user.role === 'worker'
      ? 'Verfügbarkeit & Tausch'
      : 'Servicecenter';
  const pageText = isManager(user)
    ? 'Planungsqualität, Berichte, Akten, Erinnerungen und Release-Bereitschaft.'
    : user.role === 'worker'
      ? 'Verfügbarkeiten pflegen, Schichten tauschen und Benachrichtigungen verfolgen.'
      : 'Einsatzabdeckung, Vertragsfristen, Dokumente und Benachrichtigungen.';"""
new_title = """  const pageTitle = isManager(user)
    ? 'Anfragen, Berichte & Verwaltung'
    : user.role === 'worker'
      ? 'Anfragen'
      : 'Servicecenter';
  const pageText = isManager(user)
    ? 'Freigaben, Schichttausch, Planungsqualität, Berichte und Verwaltung an einem Ort.'
    : user.role === 'worker'
      ? 'Verfügbarkeit pflegen, Schichten tauschen und Benachrichtigungen verfolgen.'
      : 'Einsatzabdeckung, Vertragsfristen, Dokumente und Benachrichtigungen.';"""
replace(operations, old_title, new_title)

# 4) Update existing E2E expectations and add explicit IA regression coverage.
test_path = "frontend/e2e/app-shell.spec.ts"
p = Path(test_path)
t = p.read_text()
t = t.replace("filter({ hasText: 'Plan' })", "filter({ hasText: 'Dienstplan' })")
t = t.replace("moreMenu.getByRole('button', { name: 'Dokumente & Lohn', exact: true })", "moreMenu.getByRole('button', { name: 'Dokumente', exact: true })", 1)
t = t.replace("moreMenu.getByRole('button', { name: 'Mehr / Steuerzentrale', exact: true })", "moreMenu.getByRole('button', { name: 'Anfragen, Berichte & Verwaltung', exact: true })")
t = t.replace("moreMenu.getByRole('button', { name: 'Dokumente & Lohn', exact: true })", "moreMenu.getByRole('button', { name: 'Lohn & Dokumente', exact: true })")
old_desktop = """    await expect(page.locator('aside')).toBeVisible();
    await expect(page.locator('.mobile-tabbar')).toBeHidden();
    await expect(page.getByTestId('admin-exception-center')).toBeVisible();

    await page.getByRole('button', { name: 'Öffnen' }).first().click();"""
new_desktop = """    await expect(page.locator('aside')).toBeVisible();
    await expect(page.locator('.mobile-tabbar')).toBeHidden();
    await expect(page.getByTestId('admin-exception-center')).toBeVisible();

    const adminNav = page.locator('aside ion-list ion-item ion-label');
    await expect(adminNav).toHaveText([
      'Übersicht',
      'Dienstplan',
      'Zeiterfassung',
      'Lohn & Dokumente',
      'Nachrichten',
      'Anfragen, Berichte & Verwaltung',
      'Personal & Kunden',
      'Aufträge & AI',
      'Verträge & ANÜ',
      'Profil',
    ]);

    await page.getByRole('button', { name: 'Öffnen' }).first().click();"""
if old_desktop not in t:
    raise SystemExit('desktop nav test anchor not found')
t = t.replace(old_desktop, new_desktop, 1)

# Add a worker desktop order check to ensure future feature additions do not scramble the learned IA.
end_anchor = """    await expectNoHorizontalPageOverflow(page);
  });
});"""
worker_test = """    await expectNoHorizontalPageOverflow(page);
  });

  test('worker desktop keeps the familiar schedule-attendance-chat-requests structure', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await mockApi(page, worker);
    await page.goto('/');

    const workerNav = page.locator('aside ion-list ion-item ion-label');
    await expect(workerNav).toHaveText([
      'Start',
      'Mein Dienstplan',
      'Zeiterfassung',
      'Nachrichten',
      'Anfragen',
      'Dokumente',
      'Meine Verträge',
      'Ranking',
      'Profil',
    ]);
  });
});"""
if end_anchor not in t:
    raise SystemExit('desktop describe closing anchor not found')
t = t.replace(end_anchor, worker_test, 1)
p.write_text(t)

print('WIW-familiar structure applied.')

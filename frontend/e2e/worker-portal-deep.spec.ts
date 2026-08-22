import { expect, Page, Route, test } from '@playwright/test';

const worker = {
  id: 'worker-deep-1',
  email: 'worker.deep@example.test',
  name: 'QA Mitarbeiter',
  first_name: 'QA',
  last_name: 'Mitarbeiter',
  role: 'worker',
  phone: '',
};

const now = Date.now();
const iso = (minutes: number) => new Date(now + minutes * 60_000).toISOString();

const baseShift = {
  id: 'shift-deep-1',
  client_name: 'QA Kunde GmbH',
  position_name: 'Servicekraft',
  location_name: 'QA Standort Frankfurt',
  starts_at: iso(30),
  ends_at: iso(390),
  break_minutes: 30,
  status: 'published',
  required_count: 2,
  filled_count: 1,
  open_count: 1,
  assigned_workers: [],
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

type MockState = {
  claimed: boolean;
  activeClock: boolean;
  correctionPending: boolean;
  availabilities: any[];
  notificationsRead: boolean;
  requests: Array<{ path: string; method: string; body: string | null }>;
};

async function mockWorkerApi(page: Page): Promise<MockState> {
  const state: MockState = {
    claimed: false,
    activeClock: false,
    correctionPending: false,
    availabilities: [],
    notificationsRead: false,
    requests: [],
  };

  await page.addInitScript(() => {
    localStorage.setItem('access', 'worker-deep-access');
    localStorage.setItem('refresh', 'worker-deep-refresh');
  });

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\//, '');
    const method = request.method();
    state.requests.push({ path, method, body: request.postData() });

    if (path === 'auth/me/') return json(route, worker);

    if (path === 'employee/home/') {
      return json(route, {
        worker: { name: worker.name, employee_number: 'QA-MA-001', employment_type: 'Teilzeit' },
        unread_notifications: state.notificationsRead ? 0 : 2,
        next_shift: state.claimed ? { ...baseShift, open_count: 0, filled_count: 2 } : null,
        month_worked_minutes: 2330,
        available_count: state.claimed ? 0 : 1,
        contract_actions: 1,
        contracts_expiring_30: 0,
        available_shifts: state.claimed ? [] : [baseShift],
      });
    }

    if (path.startsWith('shifts/available/')) {
      return json(route, state.claimed ? [] : [baseShift]);
    }
    if (path.startsWith('shifts/mine/')) {
      return json(route, state.claimed ? [{ ...baseShift, open_count: 0, filled_count: 2 }] : []);
    }
    if (path === `shifts/${baseShift.id}/claim/` && method === 'POST') {
      state.claimed = true;
      return json(route, { detail: 'Schicht übernommen.' });
    }
    if (path === `shifts/${baseShift.id}/release/` && method === 'POST') {
      state.claimed = false;
      return json(route, { detail: 'Schicht freigegeben.' });
    }

    if (path === 'attendance/home/') {
      return json(route, {
        active_entry: state.activeClock
          ? {
              id: 'entry-active',
              shift_title: 'Servicekraft',
              clock_in: iso(-15),
            }
          : null,
        eligible_shift: state.activeClock ? null : baseShift,
        month_worked_minutes: 2330,
        pending_corrections: state.correctionPending ? 1 : 0,
        history: [
          {
            id: 'entry-history-1',
            shift_title: 'Servicekraft',
            clock_in: iso(-1440),
            clock_out: iso(-1080),
          },
        ],
        corrections: state.correctionPending
          ? [{ id: 'corr-1', entry_id: 'entry-history-1', created_at: iso(-10), reason: 'QA Korrektur', status: 'pending' }]
          : [],
      });
    }
    if (path === 'time-off/' && method === 'GET') return json(route, []);
    if (path === 'time-entries/clock_in/' && method === 'POST') {
      state.activeClock = true;
      return json(route, { id: 'entry-active' });
    }
    if (path === 'time-entries/clock_out/' && method === 'POST') {
      state.activeClock = false;
      return json(route, { id: 'entry-active' });
    }
    if (path === 'attendance/entries/entry-history-1/correction/' && method === 'POST') {
      state.correctionPending = true;
      return json(route, { id: 'corr-1', status: 'pending' });
    }
    if (path === 'time-off/' && method === 'POST') return json(route, { id: 'absence-1', status: 'pending' }, 201);

    if (path === 'operations/') {
      return json(route, {
        current_worker_id: 'worker-profile-1',
        availabilities: state.availabilities,
        swaps: [],
        notifications: [
          {
            id: 'note-1',
            title: 'Neue Schicht',
            body: 'Ein neuer Einsatz ist verfügbar.',
            created_at: iso(-5),
            read_at: state.notificationsRead ? iso(-1) : null,
          },
        ],
      });
    }
    if (path === 'operations/folders/') return json(route, { workers: [], clients: [] });
    if (path === 'operations/availability/' && method === 'POST') {
      const body = JSON.parse(request.postData() || '{}');
      state.availabilities = [{ id: 'availability-1', ...body }];
      return json(route, state.availabilities[0], 201);
    }
    if (path === 'operations/availability/availability-1/' && method === 'DELETE') {
      state.availabilities = [];
      return route.fulfill({ status: 204, body: '' });
    }
    if (path === 'operations/notifications/read-all/' && method === 'POST') {
      state.notificationsRead = true;
      return json(route, { detail: 'Benachrichtigungen wurden als gelesen markiert.' });
    }
    if (path === 'operations/swaps/' && method === 'POST') return json(route, { id: 'swap-1', status: 'pending' }, 201);

    if (path.startsWith('contracts/')) {
      if (path === 'contracts/' || path.startsWith('contracts/?')) {
        return json(route, [
          {
            id: 'contract-worker-1',
            title: 'Arbeitsvertrag QA Mitarbeiter',
            kind: 'employee',
            status: 'ready',
            worker_name: worker.name,
            client_name: '',
            valid_from: new Date().toISOString().slice(0, 10),
            valid_until: null,
            signatures: [],
            pdf: null,
          },
        ]);
      }
      if (path === 'contracts/contract-worker-1/sign/' && method === 'POST') {
        return json(route, { id: 'sig-1', role: 'employee' }, 201);
      }
    }
    if (path === 'contract-templates/') return json(route, []);

    if (path === 'document-center/') {
      return json(route, {
        templates: [],
        contracts: [],
        workers: [],
        clients: [],
        payroll: [],
        documents: [],
      });
    }
    if (path === 'documents/' || path.startsWith('documents/?')) return json(route, []);

    if (path === 'conversations/') return json(route, []);
    if (path === 'users/') return json(route, []);
    if (path === 'employee/ranking/') return json(route, [
      { id: 'rank-2', employee_number: 'MA-002', ranking_points: 40, active: true, is_current_user: false, user_detail: { name: 'Lukas Schmidt' } },
      { id: 'rank-1', employee_number: 'QA-MA-001', ranking_points: 25, active: true, is_current_user: true, user_detail: { name: worker.name } },
    ]);
    if (path === 'workers/' || path.startsWith('workers/?')) return json(route, []);
    if (path === 'notifications/' || path.startsWith('notifications/?')) return json(route, []);

    if (path === 'dashboard/') return json(route, {});
    return json(route, []);
  });

  return state;
}

function forbiddenManagerFanout(state: MockState) {
  const forbidden = [
    'clients/',
    'locations/',
    'positions/',
    'orders/',
    'admin/exceptions/',
    'attendance/exceptions/',
    'working-time/settings/',
    'working-time/records/',
    'integrations/wiw/status/',
    'document-catalog/',
    'automation/orders/packages/',
  ];
  return state.requests.filter((request) => forbidden.some((prefix) => request.path.startsWith(prefix)));
}

test.describe('Worker portal deep regression QA', () => {
  test('dashboard and worker navigation stay role-scoped on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const state = await mockWorkerApi(page);
    await page.goto('/');

    await expect(page.getByRole('heading', { name: worker.name })).toBeVisible();
    await expect(page.getByText('QA-MA-001')).toBeVisible();
    await expect(page.getByText('1', { exact: true }).first()).toBeVisible();
    await expect(page.locator('.mobile-tabbar')).toBeVisible();

    await page.goto('/?view=people');
    await expect(page.getByRole('heading', { name: worker.name })).toBeVisible();
    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBeNull();

    expect(forbiddenManagerFanout(state)).toEqual([]);
  });

  test('worker can claim and release an open shift without manager APIs', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const state = await mockWorkerApi(page);
    await page.goto('/?view=schedule');

    await expect(page.getByRole('heading', { name: 'Schichten' })).toBeVisible();
    await expect(page.getByRole('button', { name: /Übernehmen/ })).toBeVisible();
    await page.getByRole('button', { name: /Übernehmen/ }).click();
    await expect.poll(() => state.claimed).toBe(true);

    await page.locator('ion-segment-button[value="mine"]').click();
    await expect(page.getByRole('button', { name: 'Freigeben' })).toBeVisible();
    await page.getByRole('button', { name: 'Freigeben' }).click();
    await expect(page.getByText('Schicht freigeben?', { exact: true })).toBeVisible();
    await page.locator('ion-alert').getByRole('button', { name: 'Freigeben' }).click();
    await expect.poll(() => state.claimed).toBe(false);
    await expect(page.getByText('Keine passenden Einsätze')).toBeVisible();

    expect(state.requests.some((r) => r.path === `shifts/${baseShift.id}/claim/` && r.method === 'POST')).toBe(true);
    expect(state.requests.some((r) => r.path === `shifts/${baseShift.id}/release/` && r.method === 'POST')).toBe(true);
    expect(forbiddenManagerFanout(state)).toEqual([]);
  });

  test('clock in/out and correction request transition through the real worker UI states', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const state = await mockWorkerApi(page);
    await page.goto('/?view=time');

    await expect(page.getByRole('heading', { name: 'Bereit für deinen Einsatz?' })).toBeVisible();
    await page.getByRole('button', { name: 'Einstempeln' }).click();
    await expect.poll(() => state.activeClock).toBe(true);
    await expect(page.getByRole('heading', { name: 'Du bist eingestempelt.' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ausstempeln' })).toBeVisible();

    await page.getByRole('button', { name: 'Ausstempeln' }).click();
    await expect.poll(() => state.activeClock).toBe(false);
    await expect(page.getByRole('heading', { name: 'Bereit für deinen Einsatz?' })).toBeVisible();

    await page.getByRole('button', { name: 'Korrektur' }).click();
    await expect(page.getByRole('heading', { name: 'Korrektur anfragen' })).toBeVisible();
    await page.getByLabel('Warum soll der Eintrag geändert werden?').fill('QA Korrektur');
    await page.getByRole('button', { name: 'Anfrage senden' }).click();
    await expect.poll(() => state.correctionPending).toBe(true);
    await expect(page.getByText('Korrektur offen')).toBeVisible();

    expect(state.requests.some((r) => r.path === 'time-entries/clock_in/' && r.method === 'POST')).toBe(true);
    expect(state.requests.some((r) => r.path === 'time-entries/clock_out/' && r.method === 'POST')).toBe(true);
    expect(state.requests.some((r) => r.path === 'attendance/entries/entry-history-1/correction/' && r.method === 'POST')).toBe(true);
    expect(forbiddenManagerFanout(state)).toEqual([]);
  });

  test('availability and notification actions work from worker operations center', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const state = await mockWorkerApi(page);
    await page.goto('/?view=operations');

    await expect(page.getByRole('heading', { name: 'Verfügbarkeit & Tausch' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Meine Verfügbarkeit' })).toBeVisible();
    await page.getByRole('button', { name: 'Eintragen' }).click();
    await expect(page.getByRole('heading', { name: 'Verfügbarkeit eintragen' })).toBeVisible();

    await page.getByLabel('Beginn').fill('2026-08-24T09:00');
    await page.getByLabel('Ende').fill('2026-08-24T18:00');
    await page.getByLabel('Hinweis').fill('QA verfügbar');
    await page.getByRole('button', { name: 'Speichern' }).click();
    await expect.poll(() => state.availabilities.length).toBe(1);
    await expect(page.getByText('QA verfügbar')).toBeVisible();

    await page.getByRole('button', { name: 'Alle gelesen' }).click();
    await expect.poll(() => state.notificationsRead).toBe(true);
    await expect(page.getByText('Neue Schicht')).toBeVisible();

    expect(state.requests.some((r) => r.path === 'operations/availability/' && r.method === 'POST')).toBe(true);
    expect(state.requests.some((r) => r.path === 'operations/notifications/read-all/' && r.method === 'POST')).toBe(true);
    expect(forbiddenManagerFanout(state)).toEqual([]);
  });

  test('worker contract action is visible while manager-only contract controls stay hidden', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const state = await mockWorkerApi(page);
    await page.goto('/?view=contracts');

    await expect(page.getByText('Arbeitsvertrag QA Mitarbeiter')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Unterschreiben' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Neuer Vertrag' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Stornieren' })).toHaveCount(0);
    expect(forbiddenManagerFanout(state)).toEqual([]);
  });

  test('worker secondary areas render without privileged API fan-out', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const state = await mockWorkerApi(page);

    await page.goto('/?view=documents');
    await expect(page.locator('body')).toContainText(/Dokument|Lohn|Keine|Noch/i);

    await page.goto('/?view=messages');
    await expect(page.getByText('Noch keine Unterhaltungen.')).toBeVisible();

    const beforeRanking = state.requests.length;
    await page.goto('/?view=ranking');
    await expect(page.getByText('Lukas Schmidt')).toBeVisible();
    await expect(page.getByText('40 Punkte')).toBeVisible();
    const rankingRequests = state.requests.slice(beforeRanking);
    expect(rankingRequests.some((r) => r.path === 'employee/ranking/')).toBe(true);
    expect(rankingRequests.some((r) => r.path === 'workers/' || r.path.startsWith('workers/?'))).toBe(false);

    expect(forbiddenManagerFanout(state)).toEqual([]);
  });
});

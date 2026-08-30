import { expect, Page, Route, test } from '@playwright/test';

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

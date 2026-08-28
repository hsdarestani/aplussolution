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
    if(path.startsWith('positions/')) return fulfill(route,[{id:'position-1',name:'Front Office',active:true}]);
    if(path.startsWith('workers/')) return fulfill(route,[]);
    return fulfill(route,[]);
  });
}

test('shift form uses 15-minute date-time picking and defaults the end six hours after start', async ({page}) => {
  await page.setViewportSize({width:390,height:844}); await mockAdmin(page); await page.goto('/?view=schedule');
  await page.getByRole('button', { name: 'Schicht anlegen' }).click();
  const start=page.getByTestId('datetime-beginn'); const end=page.getByTestId('datetime-ende');
  const startField=start.locator('ion-input[type="datetime-local"]'); const endField=end.locator('ion-input[type="datetime-local"]');
  await expect(startField).toBeVisible(); await expect(endField).toBeVisible();
  await expect(start.locator('ion-input')).toHaveCount(1); await expect(end.locator('ion-input')).toHaveCount(1);
  await expect(startField).toHaveAttribute('readonly','');
  await expect(startField).toHaveAttribute('step','900');
  await expect(startField).toHaveAttribute('data-aplus-picker-kind','datetime-local');
  await startField.evaluate((element:any)=>{element.value='2026-08-28T08:30';element.dispatchEvent(new CustomEvent('ionInput',{detail:{value:'2026-08-28T08:30'},bubbles:true,composed:true}));});
  await expect.poll(()=>startField.evaluate((element:any)=>String(element.value||''))).toContain('2026-08-28T08:30');
  await expect.poll(()=>endField.evaluate((element:any)=>String(element.value||''))).toContain('2026-08-28T14:30');
  await expect(start.getByRole('button',{name:'Heute'})).toBeVisible(); await expect(start.getByRole('button',{name:'Morgen'})).toBeVisible();
  await expect(page.getByTestId('required-count-stepper')).toBeVisible();
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth); expect(overflow).toBeLessThanOrEqual(1);
});

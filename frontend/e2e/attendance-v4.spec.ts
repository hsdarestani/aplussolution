import { expect, Page, Route, test } from '@playwright/test';

const worker = { id:'worker-u1', email:'mina@example.test', name:'Mina Berger', first_name:'Mina', last_name:'Berger', role:'worker', phone:'' };
const admin = { id:'admin-u1', email:'admin@example.test', name:'Alex Admin', first_name:'Alex', last_name:'Admin', role:'admin', phone:'' };
const shift = { id:'shift-att-1', position_name:'Servicekraft', location_name:'Messe Frankfurt', starts_at:'2026-08-15T16:00:00+02:00', ends_at:'2026-08-15T22:00:00+02:00' };

async function json(route: Route, body: unknown, status=200) { await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)}); }
async function auth(page: Page, user:any) { await page.addInitScript(()=>{localStorage.setItem('access','att-v4');localStorage.setItem('refresh','att-v4-r');}); await page.route('**/api/auth/me/',r=>json(r,user)); await page.route('**/api/dashboard/',r=>json(r,{})); }

function activeEntry(runningBreak=false) { return { id:'entry-1', worker:'wp-1', worker_name:'Mina Berger', shift:shift.id, shift_title:'Servicekraft', clock_in:'2026-08-15T16:00:00+02:00', clock_out:null, worked_minutes:60, approved:false, break_unpaid_minutes:runningBreak?0:0, break_paid_minutes:0, running_break:runningBreak?{id:'break-1',status:'running',paid:false,started_at:'2026-08-15T17:00:00+02:00',scheduled_minutes:30}:null, planned_break:runningBreak?null:{id:'break-1',status:'planned',paid:false,scheduled_minutes:30}, breaks:runningBreak?[{id:'break-1',status:'running',paid:false,started_at:'2026-08-15T17:00:00+02:00',scheduled_minutes:30}]:[{id:'break-1',status:'planned',paid:false,scheduled_minutes:30}], attestation_required:{break:false,end_of_shift:false} }; }

test('worker starts and ends a real break and gets clock-out attestation', async ({page})=>{
  await page.setViewportSize({width:390,height:844}); await auth(page,worker);
  let running=false; let clockedOut=false; const calls:string[]=[];
  await page.route('**/api/time-off/**',r=>json(r,[]));
  await page.route('**/api/attendance/home/**',r=>json(r,{ active_entry:clockedOut?null:activeEntry(running), eligible_shift:shift, policy:{allow_unscheduled_clock_in:false}, month_worked_minutes:180, pending_corrections:0, history:[], corrections:[] }));
  await page.route('**/api/attendance/breaks/start/',r=>{running=true;calls.push('break_start');return json(r,{id:'break-1',status:'running',paid:false},201);});
  await page.route('**/api/attendance/breaks/end/',r=>{running=false;calls.push('break_end');return json(r,{id:'break-1',status:'completed',paid:false,actual_minutes:30});});
  await page.route('**/api/time-entries/clock_out/',r=>{clockedOut=true;calls.push('clock_out');return json(r,{id:'entry-1',attestation_required:{break:true,end_of_shift:true}});});
  await page.route('**/api/attendance/entries/entry-1/attestation/',async r=>{const body=r.request().postDataJSON();calls.push(`attest:${body.kind}`);return json(r,{id:`att-${body.kind}`,entry:'entry-1',kind:body.kind},201);});
  await page.goto('/?view=time');
  await expect(page.getByRole('heading',{name:'Du bist eingestempelt.'})).toBeVisible();
  await page.getByRole('button',{name:'Pause starten'}).click();
  await expect.poll(()=>calls).toContain('break_start');
  await expect(page.getByRole('heading',{name:'Du bist in Pause.'})).toBeVisible();
  await page.getByRole('button',{name:'Pause beenden'}).click();
  await expect.poll(()=>calls).toContain('break_end');
  await page.getByRole('button',{name:'Ausstempeln'}).click();
  await expect(page.getByRole('heading',{name:'Schicht abschließen'})).toBeVisible();
  await page.getByRole('button',{name:'Bestätigen'}).click();
  await expect.poll(()=>calls).toEqual(expect.arrayContaining(['clock_out','attest:break','attest:end_of_shift']));
});

test('manager resolves attendance notices and can open policy/terminal controls', async ({page})=>{
  await page.setViewportSize({width:1440,height:1000}); await auth(page,admin);
  let resolved=false;
  await page.route('**/api/time-off/**',r=>json(r,[]));
  await page.route('**/api/locations/**',r=>json(r,[{id:'loc-1',name:'Messe Frankfurt'}]));
  await page.route('**/api/attendance/exceptions/**',r=>json(r,{counts:{attendance_notices:1,critical_notices:1,pending_corrections:0,unapproved_entries:0,long_running_entries:0,total:1},notices:resolved?[]:[{id:'notice-1',worker_name:'Mina Berger',notice_type:'no_show',severity:'critical',status:'open',shift_title:'Servicekraft',location_name:'Messe Frankfurt',value_minutes:35,detected_at:'2026-08-15T16:35:00+02:00'}],pending_corrections:[],unapproved_entries:[],long_running_entries:[],policies:[{id:'policy-1',name:'Standard',location:null,priority:0,early_clock_in_minutes:15,early_clock_in_mode:'off',late_clock_in_grace_minutes:5,no_show_after_minutes:30,clock_in_location_mode:'block',clock_out_location_mode:'block',required_break_after_minutes:360,required_break_minutes:30,default_break_paid:false,auto_deduct_unpaid_breaks:false,break_attestation_required:false,end_of_shift_attestation_required:false,terminal_photo_clock_in:false,terminal_photo_clock_out:false}],terminals:[]}));
  await page.route('**/api/attendance-notices/notice-1/resolve/',r=>{resolved=true;return json(r,{id:'notice-1',status:'resolved'});});
  await page.goto('/?view=time');
  await expect(page.getByRole('heading',{name:'Arbeitszeit, Abweichungen & Terminals'})).toBeVisible();
  await expect(page.getByText('Nicht erschienen',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Erledigt'}).click();
  await expect.poll(()=>resolved).toBe(true);
  await expect(page.getByRole('heading',{name:'Attendance Policy'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Kiosk-Geräte'})).toBeVisible();
});

test('public time clock terminal clocks in with device secret', async ({page})=>{
  const publicId='11111111-1111-4111-8111-111111111111';
  await page.addInitScript(({key})=>localStorage.setItem(key,'terminal-secret'),{key:`aplus:terminal:${publicId}:secret`});
  let action='';
  await page.route(`**/api/attendance/terminal/${publicId}/clock/`,async r=>{const form=await r.request().postDataBuffer(); action=form?.toString().includes('clock_in')?'clock_in':''; return json(r,{terminal:publicId,worker_name:'Mina Berger',action:'clock_in',result:{id:'entry-1'}},201);});
  await page.goto(`/terminal/${publicId}`);
  await expect(page.getByTestId('time-clock-terminal')).toBeVisible();
  await page.getByLabel('Personalnummer oder E-Mail').fill('MA-001');
  await page.getByRole('button',{name:'Einstempeln'}).click();
  await expect(page.getByText('Erfolgreich eingestempelt.')).toBeVisible();
  expect(action).toBe('clock_in');
});

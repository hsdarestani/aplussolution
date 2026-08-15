import { expect, Page, Route, test } from '@playwright/test';

const admin = { id:'admin-pay', email:'admin@example.test', name:'Alex Admin', first_name:'Alex', last_name:'Admin', role:'admin', phone:'' };
const worker = { id:'worker-pay', email:'mina@example.test', name:'Mina Berger', first_name:'Mina', last_name:'Berger', role:'worker', phone:'' };

async function json(route: Route, body: unknown, status=200) { await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)}); }
async function auth(page: Page, user:any) {
  await page.addInitScript(()=>{localStorage.setItem('access','payroll-e2e');localStorage.setItem('refresh','payroll-e2e-r');});
  await page.route('**/api/auth/me/',r=>json(r,user));
  await page.route('**/api/dashboard/',r=>json(r,{}));
  await page.route('**/api/time-off/**',r=>json(r,[]));
  await page.route('**/api/locations/**',r=>json(r,[]));
  await page.route('**/api/attendance/exceptions/**',r=>json(r,{counts:{attendance_notices:0,critical_notices:0,pending_corrections:0,unapproved_entries:0,long_running_entries:0,total:0},notices:[],pending_corrections:[],unapproved_entries:[],long_running_entries:[],policies:[],terminals:[]}));
  await page.route('**/api/attendance/home/**',r=>json(r,{active_entry:null,eligible_shift:null,policy:{allow_unscheduled_clock_in:false},month_worked_minutes:0,pending_corrections:0,history:[],corrections:[]}));
}

function entry(review='pending') { return { id:'te-snap-1',time_entry:'time-1',clock_in:'2026-08-01T08:00:00+02:00',clock_out:'2026-08-01T16:30:00+02:00',gross_minutes:510,paid_break_minutes:0,unpaid_break_minutes:30,net_minutes:480,hourly_rate:'14.50',amount_estimate:'116.00',review_status:review,reviewed_by:null,reviewed_at:null,review_note:'',locked:false,shift_title:'Servicekraft',location_name:'Messe Frankfurt' }; }
function sheet(status='open', review='pending') { return { id:'sheet-1',pay_period:'period-1',period_name:'August 2026',worker:'wp-1',worker_name:'Mina Berger',employee_number:'MA-001',status,gross_minutes:510,paid_break_minutes:0,unpaid_break_minutes:30,net_minutes:480,gross_estimate:'116.00',entry_count:1,exception_count:review==='approved'?0:1,blocking_exception_count:0,submitted_at:null,approved_at:status==='approved'?'2026-08-15T12:00:00+02:00':null,approved_by:null,locked_at:null,review_note:'',revision:1,entries:[entry(review)],exceptions:review==='approved'?[]:[{id:'exc-1',exception_type:'unapproved_entry',severity:'warning',status:'open',shift:'shift-1',time_entry:'time-1',attendance_notice:null,details:{},resolved_by:null,resolved_at:null,resolution_note:'',shift_title:'Servicekraft',created_at:'2026-08-15T10:00:00+02:00'}] }; }
function period(status='review', approved=0) { return { id:'period-1',name:'August 2026',starts_on:'2026-08-01',ends_on:'2026-08-31',status,currency:'EUR',notes:'',created_by:'admin-pay',closed_by:null,closed_at:null,locked_by:null,locked_at:null,reopen_count:0,timesheet_count:1,approved_count:approved,blocking_count:0,net_minutes:480,gross_estimate:'116.00',created_at:'2026-08-01T00:00:00+02:00',updated_at:'2026-08-15T10:00:00+02:00' }; }

test('manager reviews a timesheet and closes the pay period', async ({page})=>{
  await page.setViewportSize({width:1440,height:1000});
  await auth(page,admin);
  let review='pending'; let sheetStatus='open'; let periodStatus='review'; const calls:string[]=[];
  await page.route('**/api/pay-periods/**',async r=>{
    const url=r.request().url();
    if(url.includes('/close/')) { periodStatus='closed'; calls.push('close'); return json(r,period('closed',1)); }
    if(url.includes('/sync/')) { calls.push('sync'); return json(r,period(periodStatus,sheetStatus==='approved'?1:0)); }
    if(url.includes('/export-')) return r.fulfill({status:200,contentType:'text/csv',body:'Personalnummer;Mitarbeiter'});
    return json(r,{count:1,next:null,previous:null,results:[period(periodStatus,sheetStatus==='approved'?1:0)]});
  });
  await page.route('**/api/timesheets/**',async r=>{
    const url=r.request().url();
    if(url.includes('/approve-all-entries/')) { review='approved'; calls.push('approve_all'); return json(r,sheet(sheetStatus,review)); }
    if(url.endsWith('/approve/')) { sheetStatus='approved'; calls.push('approve_sheet'); return json(r,sheet('approved','approved')); }
    return json(r,{count:1,next:null,previous:null,results:[sheet(sheetStatus,review)]});
  });
  await page.goto('/?view=time');
  await page.getByTestId('time-tab-payroll').click();
  await expect(page.getByRole('heading',{name:'Abrechnung kontrolliert abschließen'})).toBeVisible();
  await expect(page.getByText('Mina Berger',{exact:true}).first()).toBeVisible();
  await expect(page.getByText('Zeiteintrag nicht freigegeben',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Alle Einträge freigeben'}).click();
  await expect.poll(()=>calls).toContain('approve_all');
  await page.getByRole('button',{name:'Timesheet freigeben'}).click();
  await expect.poll(()=>calls).toContain('approve_sheet');
  await expect(page.getByText('Freigegeben',{exact:true}).first()).toBeVisible();
  await page.getByRole('button',{name:'Schließen'}).click();
  await expect.poll(()=>calls).toContain('close');
  await expect(page.getByText('Geschlossen',{exact:true}).first()).toBeVisible();
});

test('worker can inspect and submit own payroll timesheet', async ({page})=>{
  await page.setViewportSize({width:390,height:844});
  await auth(page,worker);
  let status='open'; let submitted=false;
  await page.route('**/api/timesheets/**',async r=>{
    const url=r.request().url();
    if(url.includes('/submit/')) { status='submitted'; submitted=true; return json(r,sheet('submitted','approved')); }
    return json(r,{count:1,next:null,previous:null,results:[sheet(status,'approved')]});
  });
  await page.goto('/?view=time');
  await page.getByTestId('time-tab-payroll').click();
  await expect(page.getByRole('heading',{name:'Arbeitszeiten für die Abrechnung'})).toBeVisible();
  await expect(page.getByText('August 2026',{exact:true}).first()).toBeVisible();
  await expect(page.getByText('8,00 Netto-Stunden')).toBeVisible();
  await page.getByRole('button',{name:'Timesheet einreichen'}).click();
  await expect.poll(()=>submitted).toBe(true);
  await expect(page.getByText('Eingereicht',{exact:true}).first()).toBeVisible();
});

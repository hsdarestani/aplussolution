import { expect, Page, Route, test } from '@playwright/test';

const worker={id:'worker-user-v10',email:'anna@example.test',name:'Anna Becker',first_name:'Anna',last_name:'Becker',role:'worker',phone:'+49111',capabilities:[]};
const admin={id:'admin-v10',email:'admin@example.test',name:'Alex Admin',first_name:'Alex',last_name:'Admin',role:'admin',phone:'',capabilities:['schedule.view','schedule.edit','schedule.publish','attendance.view','attendance.edit']};

const ownShift={
  id:'own-shift-v10',client:'client-v10',client_name:'Messe GmbH',location:'location-v10',location_name:'Main Suites Frankfurt',location_timezone:'Europe/Berlin',
  position:'position-v10',position_name:'Servicekraft',position_color:'#445566',shift_color:'#2457E6',location_color:'#667085',order:null,order_title:'',
  starts_at:'2026-08-25T08:00:00Z',ends_at:'2026-08-25T14:00:00Z',break_minutes:30,status:'confirmed',notes:'',required_count:1,open_count:0,filled_count:1,
  required_tags:[],assignments:[{slot:'slot-own-v10',worker:'worker-profile-v10',worker_name:'Anna Becker',source:'manager_assign'}],my_confirmation:null,
  open_shift_policy:{require_approval:false,audience_mode:'eligible'},my_open_shift_request:null,open_shift_request_count:null,
};
const openShift={...ownShift,id:'open-shift-v10',starts_at:'2026-08-26T08:00:00Z',ends_at:'2026-08-26T14:00:00Z',status:'published',open_count:1,filled_count:0,assignments:[],open_shift_policy:{require_approval:true,audience_mode:'eligible'}};

async function json(route:Route,body:any,status=200){await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});}

async function mockSelfService(page:Page,user:any){
  let settings:any={
    availability_enabled:true,show_availability_to_all:false,availability_notice_days:2,team_schedule_visibility:'all',global_user_privacy:false,
    allow_shift_release:true,release_cutoff_hours:2,allow_shift_drop:true,drop_cutoff_hours:2,allow_shift_swap:true,swap_cutoff_hours:2,
    require_manager_review_swaps_drops:true,time_off_enabled:true,time_off_notice_days:2,time_off_max_paid_hours_per_day:'8.00',can_manage:user.role==='admin',
  };
  let preference={hide_contact_info:true,preferred_weekly_hours:'32.00'};
  let availability:any[]=[];
  let coverage:any[]=user.role==='admin'?[{id:'coverage-v10',kind:'drop',status:'pending_review',shift:'own-shift-v10',shift_position:'Servicekraft',shift_location:'Main Suites Frankfurt',shift_starts_at:'2026-08-25T08:00:00Z',requested_by:'worker-profile-v10',requested_by_name:'Anna Becker',offered_to:null,offered_to_name:null,offered_shift:null,note:'Familientermin'}]:[];
  let bids:any[]=user.role==='admin'?[{id:'bid-v10',shift:'open-shift-v10',position:'Servicekraft',location:'Main Suites Frankfurt',starts_at:'2026-08-26T08:00:00Z',worker:'worker-profile-v10',worker_name:'Anna Becker',status:'pending_approval',note:'Kann übernehmen'}]:[];
  let timeOff:any[]=[];
  const coworkers=[{id:'worker-profile-2-v10',name:'Lukas Schmidt',email:null,phone:null,contact_hidden:true}];
  let available=[openShift];
  let published=[openShift];

  await page.addInitScript(()=>{localStorage.setItem('access','self-service-v10');localStorage.setItem('refresh','self-service-v10-refresh');});
  await page.route('**/api/**',async route=>{
    const req=route.request();const path=new URL(req.url()).pathname.replace(/^\/api\//,'');
    if(path==='auth/me/')return json(route,user);
    if(path==='self-service/snapshot/')return json(route,{settings,preference,time_off_types:[{id:'holiday-v10',code:'holiday',name:'Urlaub',allow_paid:true,allow_unpaid:true}],coverage_pending:coverage.filter(x=>['pending_review','pending_acceptance'].includes(x.status)).length,open_shift_requests_pending:bids.filter(x=>x.status==='pending_approval').length});
    if(path==='self-service/availability/'&&req.method()==='GET')return json(route,{results:availability});
    if(path==='self-service/availability/'&&req.method()==='POST'){
      const body=req.postDataJSON();const row={id:'availability-v10',worker:'worker-profile-v10',worker_name:'Anna Becker',active:true,created_by:user.id,...body};availability=[row];return json(route,row,201);
    }
    if(path==='self-service/availability/availability-v10/'&&req.method()==='DELETE'){availability=[];return route.fulfill({status:204,body:''});}
    if(path==='self-service/coverage/'&&req.method()==='GET')return json(route,{results:coverage});
    if(path==='self-service/coverage/'&&req.method()==='POST'){
      const body=req.postDataJSON();const row={id:'coverage-created-v10',kind:body.kind,status:'pending_review',shift:body.shift,shift_position:'Servicekraft',shift_location:'Main Suites Frankfurt',shift_starts_at:ownShift.starts_at,requested_by:'worker-profile-v10',requested_by_name:'Anna Becker',offered_to:body.offered_to||null,offered_to_name:body.offered_to?'Lukas Schmidt':null,offered_shift:null,note:body.note||''};coverage=[row,...coverage];return json(route,row,201);
    }
    if(path.startsWith('self-service/coverage/')&&path.endsWith('/review/')&&req.method()==='POST'){
      const id=path.split('/')[2];const body=req.postDataJSON();coverage=coverage.map(x=>x.id===id?{...x,status:body.approve?'pending_acceptance':'denied',offered_to:body.offered_to||x.offered_to,offered_to_name:body.offered_to?'Lukas Schmidt':x.offered_to_name}:x);return json(route,coverage.find(x=>x.id===id));
    }
    if(path.startsWith('self-service/coverage/')&&path.endsWith('/cancel/')&&req.method()==='POST'){
      const id=path.split('/')[2];coverage=coverage.map(x=>x.id===id?{...x,status:'canceled'}:x);return json(route,coverage.find(x=>x.id===id));
    }
    if(path==='self-service/open-shift-requests/'&&req.method()==='GET')return json(route,{results:bids});
    if(path.startsWith('self-service/open-shift-requests/')&&path.endsWith('/decide/')&&req.method()==='POST'){
      const id=path.split('/')[2];const body=req.postDataJSON();bids=bids.map(x=>x.id===id?{...x,status:body.approve?'accepted':'denied'}:x);return json(route,bids.find(x=>x.id===id));
    }
    if(path.startsWith('self-service/open-shift-requests/')&&path.endsWith('/cancel/')&&req.method()==='POST'){
      const id=path.split('/')[2];bids=bids.map(x=>x.id===id?{...x,status:'canceled'}:x);return json(route,bids.find(x=>x.id===id));
    }
    if(path==='self-service/time-off/'&&req.method()==='GET')return json(route,{results:timeOff});
    if(path==='self-service/time-off/'&&req.method()==='POST'){
      const body=req.postDataJSON();const row={id:'timeoff-v10',worker:'worker-profile-v10',worker_name:'Anna Becker',starts_on:body.starts_on,ends_on:body.ends_on,reason:body.reason||'',status:'pending',type:body.type,type_name:'Urlaub',all_day:body.all_day,start_time:body.start_time,end_time:body.end_time,paid:body.paid,paid_hours:body.paid_hours,created_at:new Date().toISOString()};timeOff=[row];return json(route,row,201);
    }
    if(path==='self-service/coworkers/')return json(route,{visible:true,global_privacy:false,workers:coworkers});
    if(path.startsWith('self-service/team-schedule/'))return json(route,{results:[{id:'team-v10',position:'Servicekraft',location:'Main Suites Frankfurt',starts_at:'2026-08-25T08:00:00Z',ends_at:'2026-08-25T14:00:00Z',workers:['Lukas Schmidt']}]});
    if(path==='self-service/preference/'&&req.method()==='PATCH'){preference={...preference,...req.postDataJSON()};return json(route,preference);}
    if(path==='self-service/settings/'&&req.method()==='PATCH'){settings={...settings,...req.postDataJSON()};return json(route,{...settings,can_manage:true});}
    if(path==='self-service/open-shifts/open-shift-v10/policy/'&&req.method()==='PATCH'){
      const body=req.postDataJSON();published=published.map(s=>s.id==='open-shift-v10'?{...s,open_shift_policy:{...s.open_shift_policy,...body}}:s);return json(route,{shift:'open-shift-v10',require_approval:body.require_approval??true,audience_mode:body.audience_mode||'eligible',selected_workers:body.selected_workers||[]});
    }
    if(path==='shifts/mine/'&&req.method()==='GET')return json(route,{results:[ownShift]});
    if(path==='shifts/available/'&&req.method()==='GET')return json(route,{results:available});
    if(path==='shifts/open-shift-v10/claim/'&&req.method()==='POST'){
      bids=[{id:'worker-bid-v10',shift:'open-shift-v10',position:'Servicekraft',location:'Main Suites Frankfurt',starts_at:openShift.starts_at,worker:'worker-profile-v10',worker_name:'Anna Becker',status:'pending_approval',note:''}];available=[{...openShift,my_open_shift_request:{id:'worker-bid-v10',status:'pending_approval'}}];return json(route,{shift:available[0],request:{id:'worker-bid-v10',status:'pending_approval'},detail:'Bewerbung wurde zur Genehmigung gesendet.'},202);
    }
    if(path==='shifts/own-shift-v10/release/'&&req.method()==='POST')return json(route,{...ownShift,status:'published',open_count:1,filled_count:0});
    if(path.startsWith('shifts/')&&req.method()==='GET')return json(route,{results:user.role==='admin'?published:[ownShift,openShift]});
    if(path==='communications/snapshot/')return json(route,{unread_notifications:0,unread_chat:0,settings:{}});
    if(path==='notification-preferences/')return json(route,{results:[]});
    if(path==='conversations/')return json(route,{results:[]});
    if(path==='dashboard/')return json(route,{});
    if(path==='integrations/wiw/status/')return json(route,{});
    if(path==='document-catalog/')return json(route,{documents:[]});
    if(path==='operations/')return json(route,{conflicts:[],unavailable_assignments:[],coverage_gaps:[],overtime_risks:[],swaps:[],swap_candidates:[],notifications:[],pending_swaps:0,unapproved_time_entries:0,contracts_due_30:0,estimated_monthly_labor_cost:0,readiness:{}});
    if(path==='operations/folders/')return json(route,{workers:[],clients:[]});
    if(path==='workers/')return json(route,{results:[]});
    if(path==='clients/')return json(route,{results:[]});
    if(path==='locations/')return json(route,{results:[]});
    if(path==='positions/')return json(route,{results:[]});
    if(path==='orders/')return json(route,{results:[]});
    return json(route,[]);
  });
}

test('worker manages recurring availability, OpenShift bid and time off',async({page})=>{
  await page.setViewportSize({width:390,height:844});await mockSelfService(page,worker);await page.goto('/');
  await page.getByTestId('self-service-launcher').click();
  const panel=page.getByTestId('self-service-panel');await expect(panel).toBeVisible();
  await expect(panel.getByRole('heading',{name:'Meine Arbeit organisieren'})).toBeVisible();

  await panel.getByRole('button',{name:'Verfügbarkeit'}).click();
  await panel.getByLabel('Art').selectOption('unavailable');
  await panel.getByLabel('Notiz').fill('Jeden Montag blockiert');
  await panel.getByRole('button',{name:'Speichern'}).click();
  await expect(panel.getByText('Jeden Montag blockiert')).toBeVisible();

  await panel.getByRole('button',{name:'Schichten'}).click();
  await expect(panel.getByText('Bewerbung + Freigabe')).toBeVisible();
  await panel.getByRole('button',{name:'Übernehmen'}).click();
  await expect(panel.getByText('Angefragt')).toBeVisible();
  await expect(panel.getByText(/Bewerbung:/)).toBeVisible();

  await panel.getByRole('button',{name:'Abwesenheit'}).click();
  await panel.getByLabel('Ganztägig').uncheck();
  await panel.getByLabel('Grund').fill('Behördentermin');
  await panel.getByRole('button',{name:'Anfrage senden'}).click();
  await expect(panel.getByText('Behördentermin')).toBeVisible();
});

test('admin reviews bids and coverage and changes self-service policy',async({page})=>{
  await page.setViewportSize({width:1440,height:960});await mockSelfService(page,admin);await page.goto('/');
  await page.getByTestId('self-service-launcher').click();
  const panel=page.getByTestId('self-service-panel');await expect(panel).toBeVisible();
  await expect(panel.getByRole('heading',{name:'Employee Self-Service Steuerung'})).toBeVisible();

  await panel.getByRole('button',{name:/Anfragen/}).click();
  await expect(panel.getByText('Alex Admin')).toHaveCount(0);
  await expect(panel.getByText('Anna Becker')).toBeVisible();
  await panel.getByRole('button',{name:'Genehmigen'}).click();
  await expect(panel.getByText('Keine offenen Bewerbungen.')).toBeVisible();

  const target=panel.locator('.ss-list-row').filter({hasText:'Familientermin'});
  await target.locator('select').selectOption('worker-profile-2-v10');
  await target.getByRole('button',{name:'Freigeben'}).click();
  await expect(panel.getByText('Keine offenen Coverage-Prüfungen.')).toBeVisible();

  await panel.getByRole('button',{name:'Self-Service Regeln'}).click();
  const privacy=panel.locator('.ss-setting-toggle').filter({hasText:'Global User Privacy'}).locator('input');
  await privacy.check();
  await expect(privacy).toBeChecked();
  await expect(panel.getByText('OpenShift Policies')).toBeVisible();
});

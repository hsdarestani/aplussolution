import { expect, Page, Route, test } from '@playwright/test';

const admin={id:'admin-v9',email:'admin@example.test',name:'Alex Admin',first_name:'Alex',last_name:'Admin',role:'admin',phone:'',capabilities:['schedule.view','schedule.edit','schedule.publish']};
const worker={id:'worker-user-v9',email:'anna@example.test',name:'Anna Becker',first_name:'Anna',last_name:'Becker',role:'worker',phone:'',capabilities:[]};

const baseShift={
  id:'shift-v9',client:'client-v9',client_name:'Messe GmbH',location:'location-v9',location_name:'Main Suites Frankfurt',location_timezone:'Europe/Berlin',
  position:'position-v9',position_name:'Servicekraft',position_color:'#445566',shift_color:'#2457E6',location_color:'#667085',order:null,order_title:'',
  starts_at:'2026-08-18T08:00:00Z',ends_at:'2026-08-18T14:00:00Z',break_minutes:30,status:'confirmed',notes:'',required_count:1,open_count:0,filled_count:1,
  required_tags:[],assignments:[{slot:'slot-v9',worker:'worker-profile-v9',worker_name:'Anna Becker',source:'manager_assign',confirmation_status:'pending',confirmed_at:null}],
  my_confirmation:{slot:'slot-v9',status:'pending',confirmed_at:null,requested_at:'2026-08-16T06:00:00Z'},
};

async function json(route:Route,body:any,status=200){await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});}

async function selectPanelTab(panel:any, tab:string){
  await panel.locator('ion-segment').evaluate((element:HTMLElement,target:string)=>{
    const segment=element as any;
    segment.value=target;
    element.dispatchEvent(new CustomEvent('ionChange',{detail:{value:target},bubbles:true,composed:true}));
  },tab);
}

async function mockScheduler(page:Page,user:any){
  let confirmationPending=true;
  let annotations:any[]=[];
  let taskDone=false;
  let settings={allow_overlapping_open_shifts:false,require_shift_confirmation:true,can_manage:user.role==='admin'};
  let display={color_mode:'position',timezone_mode:'workplace',local_timezone:'Europe/Berlin',workplace_timezone:'Europe/Berlin',allow_overlapping_open_shifts:false,require_shift_confirmation:true,schedule_timezones:[]};
  await page.addInitScript(()=>{localStorage.setItem('access','scheduler-v9');localStorage.setItem('refresh','scheduler-v9-refresh');});
  await page.route('**/api/**',async route=>{
    const req=route.request();const path=new URL(req.url()).pathname.replace(/^\/api\//,'');
    if(path==='auth/me/')return json(route,user);
    const shift={...baseShift,assignments:baseShift.assignments.map(item=>({...item,confirmation_status:confirmationPending?'pending':'confirmed'})),my_confirmation:user.role==='worker'?{...baseShift.my_confirmation,status:confirmationPending?'pending':'confirmed'}:null};
    if(path==='shifts/'&&req.method()==='GET')return json(route,{results:[shift]});
    if(path==='shifts/available/'&&req.method()==='GET')return json(route,{results:[]});
    if(path==='shifts/mine/'&&req.method()==='GET')return json(route,{results:[shift]});
    if(path==='scheduling/confirmations/slot-v9/confirm/'&&req.method()==='POST'){confirmationPending=false;return json(route,{slot:'slot-v9',status:'confirmed',confirmed_at:new Date().toISOString()});}
    if(path==='scheduling/confirmations/')return json(route,{results:confirmationPending?[{id:'confirmation-v9',slot:'slot-v9',shift:'shift-v9',position:'Servicekraft',location:'Main Suites Frankfurt',starts_at:baseShift.starts_at,ends_at:baseShift.ends_at,status:'pending',requested_at:'2026-08-16T06:00:00Z',confirmed_at:null}]:[],pending_count:confirmationPending?1:0});
    if(path==='workers/')return json(route,{results:[{id:'worker-profile-v9',employee_number:'MA-001',active:true,user_detail:{name:'Anna Becker',email:'anna@example.test'}}]});
    if(path==='clients/')return json(route,{results:[{id:'client-v9',name:'Messe GmbH'}]});
    if(path==='locations/')return json(route,{results:[{id:'location-v9',name:'Main Suites Frankfurt',client:'client-v9',timezone:'Europe/Berlin'}]});
    if(path==='positions/')return json(route,{results:[{id:'position-v9',name:'Servicekraft',color:'#445566'}]});
    if(path==='orders/')return json(route,{results:[]});
    if(path==='skill-tags/')return json(route,{results:[]});
    if(path==='schedule-groups/')return json(route,{results:[{id:'schedule-v9',name:'Frankfurt',timezone:'Europe/Berlin',active:true}]});
    if(path==='scheduler-colors/')return json(route,{results:[]});
    if(path==='scheduling/display-preferences/'&&req.method()==='GET')return json(route,display);
    if(path==='scheduling/display-preferences/'&&req.method()==='PATCH'){display={...display,...req.postDataJSON()};return json(route,display);}
    if(path==='scheduling/completion-settings/'&&req.method()==='GET')return json(route,settings);
    if(path==='scheduling/completion-settings/'&&req.method()==='PATCH'){settings={...settings,...req.postDataJSON()};return json(route,settings);}
    if(path==='scheduling/completion-snapshot/')return json(route,{
      annotations,
      task_lists:[{id:'task-list-v9',title:'Opening',work_date:'2026-08-18',notes:'Vor Öffnung',schedule:null,schedule_name:'',location:'location-v9',location_name:'Main Suites Frankfurt',active:true,created_by:null,created_at:'2026-08-16T06:00:00Z',updated_at:'2026-08-16T06:00:00Z',completed_count:taskDone?1:0,task_count:1,tasks:[{id:'task-v9',task_list:'task-list-v9',title:'Eingang prüfen',position:null,position_name:'',assignee:'worker-profile-v9',assignee_name:'Anna Becker',completed_at:taskDone?new Date().toISOString():null,completed_by:null,completed_by_name:'',completed:taskDone,sort_order:0,created_at:'2026-08-16T06:00:00Z',updated_at:'2026-08-16T06:00:00Z'}]}],
      display,pending_confirmations:confirmationPending?1:0,
    });
    if(path==='schedule-annotations/'&&req.method()==='POST'){const body=req.postDataJSON();const row={id:'annotation-v9',...body,location_name:body.location?'Main Suites Frankfurt':'',schedule_name:'',active:true,created_by:null,created_by_name:'',created_at:new Date().toISOString(),updated_at:new Date().toISOString(),business_closed_result:{changed:0,skipped:[]}};annotations=[row];return json(route,row,201);}
    if(path==='schedule-task-lists/'&&req.method()==='GET')return json(route,{results:[]});
    if(path==='schedule-tasks/task-v9/complete/'&&req.method()==='POST'){taskDone=!!req.postDataJSON().completed;return json(route,{id:'task-v9',title:'Eingang prüfen',completed_at:taskDone?new Date().toISOString():null,completed:taskDone});}
    if(path==='scheduling/copy-range/'&&req.method()==='POST')return json(route,{created:['copied-shift-v9'],warnings:[]});
    if(path==='communications/snapshot/')return json(route,{unread_notifications:0,unread_chat:0,channels:[],notifications:[],settings:{}});
    if(path==='notification-preferences/')return json(route,{results:[]});
    if(path==='conversations/')return json(route,{results:[]});
    if(path==='dashboard/')return json(route,{});
    if(path==='integrations/wiw/status/')return json(route,{});
    if(path==='document-catalog/')return json(route,{documents:[]});
    if(path==='operations/')return json(route,{conflicts:[],unavailable_assignments:[],coverage_gaps:[],overtime_risks:[],swaps:[],swap_candidates:[],notifications:[],pending_swaps:0,unapproved_time_entries:0,contracts_due_30:0,estimated_monthly_labor_cost:0,readiness:{}});
    if(path==='operations/folders/')return json(route,{workers:[],clients:[]});
    return json(route,[]);
  });
}

test('admin manages scheduler completion extras without leaving the schedule',async({page})=>{
  await page.setViewportSize({width:1440,height:1000});await mockScheduler(page,admin);await page.goto('/?view=schedule');
  await expect(page.getByRole('heading',{name:'Personalbedarf & Schichten'})).toBeVisible();
  await page.getByRole('button',{name:'Plan-Extras'}).click();
  const panel=page.getByTestId('scheduler-completion-panel');await expect(panel).toBeVisible();
  await expect(panel.getByRole('heading',{name:'Plan-Extras'})).toBeVisible();
  await panel.locator('ion-input').filter({hasText:'Titel'}).first().locator('input').fill('Team Briefing');
  await panel.getByRole('button',{name:'Annotation speichern'}).click();
  await expect(panel.getByText('Team Briefing',{exact:true})).toBeVisible();

  await panel.locator('ion-segment-button[value="copy"]').click();
  await panel.getByRole('button',{name:'Zeitraum kopieren'}).click();
  await expect(panel.getByText(/1 Schicht\(en\) kopiert/)).toBeVisible();

  await panel.locator('ion-segment-button[value="settings"]').click();
  await expect(panel.getByText('Überlappende OpenShifts erlauben',{exact:true})).toBeVisible();
  const overlap=panel.locator('.sc-toggle').filter({hasText:'Überlappende OpenShifts erlauben'}).locator('ion-toggle');
  await overlap.click();
  await expect(overlap).toHaveJSProperty('checked',true);

  await panel.locator('ion-segment-button[value="display"]').click();
  await expect(panel.getByText('Farbcodierung',{exact:true})).toBeVisible();
  await expect(panel.getByText('Zeitzone',{exact:true})).toBeVisible();
});

test('worker confirms own shift and completes only surfaced task',async({page})=>{
  await page.setViewportSize({width:390,height:844});await mockScheduler(page,worker);await page.goto('/?view=schedule');
  await expect(page.getByRole('heading',{name:'Schichten'})).toBeVisible();
  await page.locator('ion-segment-button[value="mine"]').click();
  await expect(page.getByRole('button',{name:'Bestätigen'})).toBeVisible();
  await page.getByRole('button',{name:'Bestätigen'}).click();
  await expect(page.getByRole('button',{name:'Bestätigen'})).toHaveCount(0);

  await page.getByRole('button',{name:'Planinfos'}).click();
  const panel=page.getByTestId('scheduler-completion-panel');await expect(panel).toBeVisible();
  await expect(panel.getByText('Keine offene Schichtbestätigung.',{exact:true})).toBeVisible();
  await selectPanelTab(panel,'tasks');
  await expect(panel.locator('.task-list')).toHaveCount(1);
  const taskRow=panel.locator('.task-items label').filter({hasText:'Eingang prüfen'});
  await expect(taskRow).toHaveCount(1);
  await expect(taskRow).toContainText('Eingang prüfen');
  await expect(taskRow).toContainText('Anna Becker');
  await expect(panel.locator('.task-items label').filter({hasText:'Fremde Aufgabe'})).toHaveCount(0);
  const checkbox=taskRow.locator('ion-checkbox');
  await checkbox.click();
  await expect(taskRow.locator('span')).toHaveClass(/done/);
  await expect(panel.locator('ion-segment-button[value="settings"]')).toHaveCount(0);
});

import { expect, Page, Route, test } from '@playwright/test';

const admin = {id:'admin-workplace',email:'admin@example.test',name:'Alex Admin',first_name:'Alex',last_name:'Admin',role:'admin',phone:'',capabilities:['workplace.view','workplace.manage','roles.view','roles.manage']};
const supervisor = {id:'manager-workplace',email:'supervisor@example.test',name:'Sina Supervisor',first_name:'Sina',last_name:'Supervisor',role:'manager',phone:'',capabilities:['manager.access','workplace.view','people.view','schedule.view','attendance.view'],access_scope:{mode:'scoped',role:'supervisor',wage_visibility:'scoped'}};
const role = {id:'role-supervisor',code:'supervisor',name:'Supervisor',description:'Operative Führung',permissions:['manager.access','workplace.view','people.view','schedule.view','attendance.view'],wage_visibility:'scoped',is_system:true,active:true,assignment_count:1};
const settings = {id:'settings-1',company_name:'A+ Solution GmbH',timezone:'Europe/Berlin',week_starts_on:0,time_format:'24h',currency:'EUR',overtime_daily_hours:'8.00',overtime_weekly_hours:'40.00',overtime_mode:'warn',overtime_multiplier:'1.25',labor_sharing_enabled:true,manager_can_manage_roles:false};

async function json(route:Route, body:unknown, status=200){await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});}
async function mock(page:Page,user:any,onSettings?:(body:any)=>void,onAssignment?:(body:any)=>void){
  await page.addInitScript(()=>{localStorage.setItem('access','workplace-e2e');localStorage.setItem('refresh','workplace-e2e-r');});
  await page.route('**/api/**',async route=>{
    const req=route.request(); const url=new URL(req.url()); const path=url.pathname.replace(/^\/api\//,'');
    if(path==='auth/me/') return json(route,user);
    if(path==='workplace/snapshot/') return json(route,{
      settings,roles:[role],assignments:user.role==='manager'?[{id:'assign-1',user:user.id,user_name:user.name,access_role:role.id,role_name:'Supervisor',role_code:'supervisor',scope_mode:'scoped',schedule_groups:[],schedule_names:['Frankfurt'],locations:['loc-1'],location_names:['Frankfurt'],workers:['worker-1'],worker_names:['Mina Berger'],can_share_labor:false,active:true,capabilities:supervisor.capabilities}]:[],capability_catalog:['manager.access','workplace.view','workplace.manage','roles.view','roles.manage','people.view','schedule.view'],current_user:{capabilities:user.capabilities,scope:user.access_scope||{mode:'all'}},managers:[{id:admin.id,name:admin.name,email:admin.email,role:'admin'},{id:supervisor.id,name:supervisor.name,email:supervisor.email,role:'manager'}],workers:[{id:'worker-1',name:'Mina Berger',employee_number:'MA-001'}],schedules:[{id:'schedule-1',name:'Frankfurt'}],locations:[{id:'loc-1',name:'Frankfurt'}],can_manage_settings:user.role==='admin',can_manage_roles:user.role==='admin'
    });
    if(path==='workplace/settings/'&&req.method()==='PATCH'){const body=req.postDataJSON();onSettings?.(body);return json(route,{...settings,...body});}
    if(path==='access-assignments/'&&req.method()==='POST'){const body=req.postDataJSON();onAssignment?.(body);return json(route,{id:'assign-new',...body});}
    if(path==='operations/') return json(route,{});
    if(path==='operations/folders/') return json(route,{workers:[],clients:[]});
    if(path==='integrations/wiw/status/') return json(route,{});
    if(path==='document-catalog/') return json(route,{documents:[],counts:{}});
    if(path==='working-time/settings/') return json(route,{employees:[]});
    if(path==='working-time/records/'||path==='automation/orders/packages/'||path.startsWith('shifts/')||path.startsWith('absence-cases/')||path.startsWith('coverage-offers/')) return json(route,[]);
    if(path==='dashboard/') return json(route,{});
    return json(route,[]);
  });
}

test('admin edits workplace rules and creates a scoped assignment',async({page})=>{
  await page.setViewportSize({width:1440,height:1000});
  let saved:any=null; let assigned:any=null;
  await mock(page,admin,b=>saved=b,b=>assigned=b);
  await page.goto('/?view=operations');
  await expect(page.getByTestId('workplace-admin-panel')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Betrieb, Rollen & Berechtigungen'})).toBeVisible();
  await expect(page.getByText('Supervisor',{exact:true}).first()).toBeVisible();
  const currency=page.locator('ion-input').filter({hasText:'Währung'});
  await currency.locator('input').fill('CHF');
  await page.getByRole('button',{name:'Speichern',exact:true}).first().click();
  await expect.poll(()=>saved?.currency).toBe('CHF');
  await page.getByRole('button',{name:'Zuweisen'}).click();

  const assignmentModal=page.locator('ion-modal.show-modal').filter({hasText:'Neue Zuweisung'}).last();
  await expect(assignmentModal).toBeVisible();
  await assignmentModal.locator('ion-select').filter({hasText:'Benutzer'}).click();
  const userAlert=page.locator('ion-alert').last();
  await expect(userAlert).toBeVisible();
  await userAlert.getByRole('radio',{name:/^Sina Supervisor/}).click();
  await userAlert.getByRole('button',{name:'OK',exact:true}).click();
  await expect(userAlert).toBeHidden();

  await assignmentModal.locator('ion-select').filter({hasText:'Rolle'}).click();
  const roleAlert=page.locator('ion-alert').last();
  await expect(roleAlert).toBeVisible();
  await roleAlert.getByRole('radio',{name:'Supervisor',exact:true}).click();
  await roleAlert.getByRole('button',{name:'OK',exact:true}).click();
  await expect(roleAlert).toBeHidden();

  await assignmentModal.locator('.workplace-modal-actions ion-button').filter({hasText:'Speichern'}).click();
  await expect.poll(()=>assigned?.scope_mode).toBe('scoped');
  await expect.poll(()=>assigned?.user).toBe(supervisor.id);
});

test('scoped supervisor sees own effective access without admin controls',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await mock(page,supervisor);
  await page.goto('/?view=operations');
  await expect(page.getByTestId('workplace-admin-panel')).toBeVisible();
  await expect(page.getByText('Zugeordneter Bereich')).toBeVisible();
  await expect(page.getByText(/Mina Berger/)).toBeVisible();
  await expect(page.getByRole('button',{name:'Zuweisen'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Eigene Rolle'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Speichern',exact:true})).toHaveCount(0);
});

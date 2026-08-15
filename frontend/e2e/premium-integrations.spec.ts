import { expect, Page, Route, test } from '@playwright/test';

const admin={id:'admin-int',email:'admin@example.test',name:'Alex Admin',first_name:'Alex',last_name:'Admin',role:'admin',phone:'',capabilities:['workplace.manage','payroll.export']};
const supervisor={id:'manager-int',email:'manager@example.test',name:'Sina Supervisor',first_name:'Sina',last_name:'Supervisor',role:'manager',phone:'',capabilities:['manager.access','workplace.view','schedule.view']};
async function json(route:Route,body:unknown,status=200){await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});}

async function mock(page:Page,user:any){
  let keys:any[]=[];let hooks:any[]=[];let saml:any[]=[];let connectors:any[]=[];
  await page.addInitScript(()=>{localStorage.setItem('access','integrations-e2e');localStorage.setItem('refresh','integrations-e2e-r');});
  await page.route('**/api/**',async route=>{
    const req=route.request();const path=new URL(req.url()).pathname.replace(/^\/api\//,'');
    if(path==='auth/me/')return json(route,user);
    if(path==='integrations/api-keys/'&&req.method()==='GET')return json(route,{scopes:['workers.read','shifts.read','timesheets.read','payroll.export','webhooks.write'],results:keys});
    if(path==='integrations/api-keys/'&&req.method()==='POST'){const body=req.postDataJSON();const row={id:'key-1',name:body.name,prefix:'abc123',scopes:body.scopes,active:true};keys=[row];return json(route,{...row,token:'awf_abc123_secret-once'},201);}
    if(path==='integrations/webhooks/'&&req.method()==='GET')return json(route,{results:hooks});
    if(path==='integrations/webhooks/'&&req.method()==='POST'){const body=req.postDataJSON();const row={id:'hook-1',name:body.name,url:body.url,event_types:body.event_types,active:true,timeout_seconds:10,max_attempts:6};hooks=[row];return json(route,{...row,secret:'webhook-secret-once'},201);}
    if(path==='integrations/webhook-deliveries/')return json(route,{results:[]});
    if(path==='integrations/saml/providers/'&&req.method()==='GET')return json(route,{results:saml});
    if(path==='integrations/saml/providers/'&&req.method()==='POST'){const body=req.postDataJSON();const row={id:'saml-1',...body};saml=[row];return json(route,row,201);}
    if(path==='integrations/payroll/connectors/'&&req.method()==='GET')return json(route,{results:connectors});
    if(path==='integrations/payroll/connectors/'&&req.method()==='POST'){const body=req.postDataJSON();const row={id:'pay-1',name:body.name,provider:body.provider,configuration:body.configuration,active:true,has_credentials:false};connectors=[row];return json(route,row,201);}
    if(path.startsWith('pay-periods/'))return json(route,{results:[{id:'period-1',name:'August 2026',status:'closed',starts_on:'2026-08-01',ends_on:'2026-08-31'}]});
    if(path==='workplace/snapshot/')return json(route,{settings:{company_name:'A+ Solution GmbH',timezone:'Europe/Berlin',week_starts_on:0,time_format:'24h',currency:'EUR',overtime_daily_hours:'8.00',overtime_weekly_hours:'40.00',overtime_mode:'warn',overtime_multiplier:'1.25',labor_sharing_enabled:false,manager_can_manage_roles:false},roles:[],assignments:[],capability_catalog:[],managers:[],workers:[],schedules:[],locations:[],current_user:{capabilities:user.capabilities,scope:{mode:'all'}},can_manage_settings:user.role==='admin',can_manage_roles:user.role==='admin'});
    if(path==='operations/')return json(route,{});if(path==='operations/folders/')return json(route,{workers:[],clients:[]});if(path==='integrations/wiw/status/')return json(route,{});if(path==='document-catalog/')return json(route,{documents:[],counts:{}});if(path==='working-time/settings/')return json(route,{employees:[]});if(path==='dashboard/')return json(route,{});
    if(path.startsWith('shifts/')||path.startsWith('absence-cases/')||path.startsWith('coverage-offers/')||path.startsWith('automation/orders/packages/'))return json(route,[]);
    return json(route,[]);
  });
}

test('admin manages premium integrations and receives secrets only on create',async({page})=>{
  await page.setViewportSize({width:1440,height:1050});await mock(page,admin);await page.goto('/?view=operations');
  const panel=page.getByTestId('premium-integrations-panel');await expect(panel).toBeVisible();await expect(panel.getByRole('heading',{name:'Premium Integrationen'})).toBeVisible();

  await panel.locator('ion-input').filter({hasText:'Name'}).first().locator('input').fill('BI Export');
  await panel.getByRole('button',{name:'API Key erstellen'}).click();
  await expect(panel.getByText('awf_abc123_secret-once',{exact:true})).toBeVisible();
  await expect(panel.getByText('BI Export',{exact:true}).last()).toBeVisible();
  await panel.getByRole('button',{name:'Schließen'}).click();
  await expect(panel.getByText('awf_abc123_secret-once',{exact:true})).toHaveCount(0);

  await panel.locator('ion-segment-button[value="webhooks"]').click();
  const hookCard=panel.locator('ion-card').filter({hasText:'Webhook Endpoint'});
  await hookCard.locator('ion-input').filter({hasText:'Name'}).locator('input').fill('ERP');
  await hookCard.locator('ion-input').filter({hasText:'HTTPS URL'}).locator('input').fill('https://hooks.example.com/workforce');
  await hookCard.getByRole('button',{name:'Webhook erstellen'}).click();
  await expect(panel.getByText('webhook-secret-once',{exact:true})).toBeVisible();
  await panel.getByRole('button',{name:'Schließen'}).click();

  await panel.locator('ion-segment-button[value="saml"]').click();
  const samlCard=panel.locator('ion-card').filter({hasText:'SAML v2 Identity Provider'});
  await samlCard.locator('ion-input').filter({hasText:'IdP Entity ID'}).locator('input').fill('https://idp.example.test/entity');
  await samlCard.locator('ion-input').filter({hasText:'SSO URL'}).locator('input').fill('https://idp.example.test/sso');
  await samlCard.locator('ion-textarea').locator('textarea').fill('-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----');
  await samlCard.getByRole('button',{name:'SSO Provider speichern'}).click();
  const samlRow=panel.locator('.pi-list article').filter({hasText:'Company SSO'});
  await expect(samlRow).toContainText('https://idp.example.test/entity');

  await panel.locator('ion-segment-button[value="payroll"]').click();
  await panel.getByRole('button',{name:'Connector erstellen'}).click();
  await expect(panel.getByText('DATEV',{exact:true}).last()).toBeVisible();
});

test('manager without workplace manage never receives integration controls',async({page})=>{
  await page.setViewportSize({width:390,height:844});await mock(page,supervisor);await page.goto('/?view=operations');
  await expect(page.getByTestId('premium-integrations-panel')).toHaveCount(0);
});

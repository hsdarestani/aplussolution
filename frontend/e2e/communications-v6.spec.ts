import { expect, Page, Route, test } from '@playwright/test';

const worker={id:'worker-comms',email:'worker@example.test',name:'Anna Becker',first_name:'Anna',last_name:'Becker',role:'worker',phone:'',capabilities:['schedule.view','attendance.view']};
const admin={id:'admin-comms',email:'admin@example.test',name:'Alex Admin',first_name:'Alex',last_name:'Admin',role:'admin',phone:'',capabilities:['workplace.manage']};
const colleague={id:'worker-2',email:'lukas@example.test',name:'Lukas Schmidt',role:'worker'};
const workplace={id:'channel-workplace',title:'A+ Solution GmbH',channel_type:'workplace',pinned:true,unread_count:1,can_post:false,can_manage:false,can_leave:false,muted:false,participants_detail:[worker,colleague],messages:[{id:'m1',sender:colleague.id,sender_detail:colleague,body:'Morgen bitte 10 Minuten früher da sein.',created_at:'2026-08-15T16:00:00Z',mine:false,read_count:0}]};
const prefs=[{id:'pref-workchat',category:'workchat',category_label:'WorkChat',in_app_enabled:true,push_enabled:true,email_enabled:false,sms_enabled:false,reminder_minutes:1440},{id:'pref-reminder',category:'shift_reminder',category_label:'Schichterinnerungen',in_app_enabled:true,push_enabled:true,email_enabled:true,sms_enabled:false,reminder_minutes:1440}];
const notice={id:'notice-1',title:'Dienstplan aktualisiert',body:'Samstag 18:00 – Messe Frankfurt',category:'schedule_update',priority:'normal',action_url:'/schedule',is_read:false,created_at:'2026-08-15T17:00:00Z',data:{}};

async function json(route:Route,body:unknown,status=200){await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});}
async function mock(page:Page,user:any){
  let channels:any[]=[{...workplace,can_post:user.role==='admin',can_manage:user.role==='admin'}];
  let notices:any[]=[notice];
  let preferences=structuredClone(prefs);
  let settings={id:'comms-settings',workchat_enabled:true,employees_can_post_workplace:false,users_can_create_channels:false,images_enabled:true,sms_fallback_enabled:false,can_manage:user.role==='admin'};
  await page.addInitScript(()=>{localStorage.setItem('access','comms-e2e');localStorage.setItem('refresh','comms-e2e-r');});
  await page.route('**/api/**',async route=>{
    const req=route.request();const url=new URL(req.url());const path=url.pathname.replace(/^\/api\//,'');
    if(path==='auth/me/')return json(route,user);
    if(path==='communications/snapshot/')return json(route,{unread_notifications:notices.filter(x=>!x.is_read).length,unread_chat:channels.reduce((n,x)=>n+x.unread_count,0),devices:1,settings});
    if(path==='conversations/'&&req.method()==='GET')return json(route,channels);
    if(path==='conversations/'&&req.method()==='POST'){
      const body=req.postDataJSON();const created={id:'channel-new',title:body.title||'Neue Gruppe',channel_type:body.participants.length===1?'direct':'group',pinned:false,unread_count:0,can_post:true,can_manage:true,can_leave:true,muted:false,participants_detail:[user,colleague],messages:[]};channels=[created,...channels];return json(route,created,201);
    }
    if(path.match(/^conversations\/[^/]+\/mark_read\/$/)){const id=path.split('/')[1];channels=channels.map(x=>x.id===id?{...x,unread_count:0}:x);return json(route,{read_at:new Date().toISOString()});}
    if(path.match(/^conversations\/[^/]+\/post_message\/$/)){const id=path.split('/')[1];const body=req.postData()?.includes('{')?req.postDataJSON().body:'Neue Nachricht';const msg={id:'msg-new',sender:user.id,sender_detail:user,body,created_at:new Date().toISOString(),mine:true,read_count:0};channels=channels.map(x=>x.id===id?{...x,messages:[...(x.messages||[]),msg]}:x);return json(route,msg,201);}
    if(path.match(/^conversations\/[^/]+\/mute\/$/))return json(route,{muted:true,notifications_enabled:true});
    if(path==='communications/candidates/')return json(route,[colleague]);
    if(path==='notifications/'&&req.method()==='GET')return json(route,notices);
    if(path==='notifications/mark_all_read/'&&req.method()==='POST'){notices=notices.map(x=>({...x,is_read:true}));return json(route,{updated:notices.length});}
    if(path.match(/^notifications\/[^/]+\/mark_read\/$/)){notices=notices.map(x=>({...x,is_read:true}));return json(route,{...notice,is_read:true});}
    if(path.match(/^notifications\/[^/]+\/$/)&&req.method()==='DELETE'){notices=[];return route.fulfill({status:204,body:''});}
    if(path==='notification-preferences/'&&req.method()==='GET')return json(route,preferences);
    if(path.match(/^notification-preferences\/[^/]+\/configure\/$/)&&req.method()==='PATCH'){const id=path.split('/')[1];const patch=req.postDataJSON();preferences=preferences.map(x=>x.id===id?{...x,...patch}:x);return json(route,preferences.find(x=>x.id===id));}
    if(path==='communications/settings/'&&req.method()==='GET')return json(route,settings);
    if(path==='communications/settings/'&&req.method()==='PATCH'){settings={...settings,...req.postDataJSON()};return json(route,settings);}
    if(path==='push-devices/'&&req.method()==='POST')return json(route,{id:'device-1',...req.postDataJSON()},201);
    if(path==='operations/'||path==='operations/folders/'||path==='integrations/wiw/status/'||path==='document-catalog/'||path==='working-time/settings/'||path==='dashboard/')return json(route,{});
    return json(route,[]);
  });
}

test('worker uses WorkChat, notification center and per-category alert preferences',async({page})=>{
  await mock(page,worker);await page.goto('/');
  await expect(page.getByTestId('communications-dock')).toBeVisible();
  await page.getByRole('button',{name:'WorkChat anzeigen'}).click();
  await expect(page.getByRole('heading',{name:'WorkChat & Benachrichtigungen'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'A+ Solution GmbH',exact:true})).toBeVisible();
  await expect(page.getByText('Morgen bitte 10 Minuten früher da sein.')).toBeVisible();
  await expect(page.getByPlaceholder('Dieser Kanal ist nur für Ankündigungen.')).toBeDisabled();

  await page.getByRole('button',{name:/Benachrichtigungen/}).last().click();
  await expect(page.getByText('Dienstplan aktualisiert')).toBeVisible();
  await page.getByRole('button',{name:'Alle gelesen'}).click();

  await page.getByRole('button',{name:'Einstellungen'}).click();
  await expect(page.getByText('Alert Preferences')).toBeVisible();
  const workchatRow=page.locator('.comms-pref-grid article').filter({hasText:'WorkChat'});
  const email=workchatRow.getByText('E-Mail').locator('input');
  await expect(email).not.toBeChecked();
  await email.click();
  await expect(email).toBeChecked();
});

test('admin creates a scoped group channel and manages WorkChat global rules',async({page})=>{
  await mock(page,admin);await page.goto('/');
  await page.getByRole('button',{name:'WorkChat anzeigen'}).click();
  await page.locator('.comms-aside-head button').click();
  await expect(page.getByRole('heading',{name:'Neuer WorkChat-Kanal'})).toBeVisible();
  await page.getByPlaceholder('Gruppenname (optional)').fill('Messe Team');
  await page.locator('.comms-candidates label').filter({hasText:'Lukas Schmidt'}).locator('input').check();
  await page.getByRole('button',{name:'Kanal erstellen'}).click();
  await expect(page.getByRole('heading',{name:'Messe Team',exact:true})).toBeVisible();

  await page.getByRole('button',{name:'Einstellungen'}).click();
  await page.getByRole('button',{name:'WorkChat Regeln'}).click();
  const rules=page.locator('.comms-settings-card');
  await expect(rules).toBeVisible();
  const employeePost=rules.getByText('Mitarbeiter dürfen posten').locator('input');
  await employeePost.click();
  await expect(employeePost).toBeChecked();
});

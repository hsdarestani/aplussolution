import { expect, Route, test } from '@playwright/test';

const admin={id:'admin-akte',email:'admin@example.test',name:'A+ Admin',first_name:'A+',last_name:'Admin',role:'admin',phone:''};
const worker={id:'worker-akte-1',employee_number:'MA-100',employment_type:'teilzeit',monthly_hours:'80.00',tariff_hourly_rate:'16.50',extra_allowance:'1.50',ranking_points:10,active:true,user_detail:{id:'user-worker-1',name:'Anna Becker',first_name:'Anna',last_name:'Becker',email:'anna@example.test',phone:'+4969123',role:'worker'}};
let akte:any={kind:'worker',title:'Anna Becker',number:'MA-100',profile:worker,master_data:{data:{street:'Musterstraße 1',postal_code:'60311',city:'Frankfurt am Main'}},summary:{contracts:1,documents:1,payroll:1,shifts:1},contracts:[{id:'c1',title:'Arbeitsvertrag',status:'signed',starts_on:'2026-08-01',pdf:'/media/c1.pdf'}],document_folders:[{key:'general',label:'Allgemein',count:1,items:[{id:'d1',title:'Ausweis',created_at:'2026-08-22T07:00:00Z',file:'/media/d1.pdf'}]}],payroll:[{id:'p1',period:'2026-08',created_at:'2026-08-22T07:00:00Z',document:'/media/p1.pdf'}],shifts:[{id:'s1',position_name:'Serviceleitung',location_name:'Evangelische Akademie',client_name:'Kunde GmbH',status:'confirmed',starts_at:'2026-08-23T07:00:00Z',ends_at:'2026-08-23T12:00:00Z'}]};

async function json(route:Route,body:unknown,status=200){await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});}

test.beforeEach(async({page})=>{
  await page.addInitScript(()=>{localStorage.setItem('access','akte-access');localStorage.setItem('refresh','akte-refresh');});
  await page.route('**/api/**',async route=>{
    const req=route.request(); const path=new URL(req.url()).pathname.replace(/^\/api\//,'');
    if(path==='auth/me/')return json(route,admin);
    if(path==='workers/worker-akte-1/akte/'&&req.method()==='GET')return json(route,akte);
    if(path==='workers/worker-akte-1/akte/'&&req.method()==='PATCH'){
      const payload=req.postDataJSON(); akte={...akte,profile:{...akte.profile,user_detail:{...akte.profile.user_detail,first_name:payload.profile.first_name,name:`${payload.profile.first_name} ${payload.profile.last_name}`},employee_number:payload.profile.employee_number},master_data:{data:payload.master_data}}; return json(route,akte);
    }
    if(path==='notifications/?page=1'||path.startsWith('notifications/'))return json(route,{results:[]});
    if(path==='workers/'||path.startsWith('workers/?'))return json(route,{results:[worker],next:null});
    if(path==='clients/'||path.startsWith('clients/?'))return json(route,{results:[],next:null});
    return json(route,{});
  });
});

test('German UI is marked notranslate and Digital Akte is a dedicated editable page with Berlin time',async({page})=>{
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('/?view=akte&akte_kind=worker&akte_id=worker-akte-1');
  await expect(page.getByTestId('akte-page')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Anna Becker'})).toBeVisible();
  await expect(page.getByText('23.08.2026, 09:00')).toBeVisible();
  expect(await page.locator('html').getAttribute('lang')).toBe('de');
  expect(await page.locator('html').getAttribute('translate')).toBe('no');
  await expect(page.locator('meta[name="google"][content="notranslate"]')).toHaveCount(1);

  await page.getByRole('button',{name:'Profil bearbeiten'}).click();
  await page.getByLabel('Vorname').fill('Anna Maria');
  const saveRequest=page.waitForRequest(req=>req.url().includes('/api/workers/worker-akte-1/akte/')&&req.method()==='PATCH');
  await page.getByRole('button',{name:'Änderungen speichern'}).click();
  const request=await saveRequest;
  expect(request.postDataJSON().profile.first_name).toBe('Anna Maria');
  await expect(page.getByRole('button',{name:'Profil bearbeiten'})).toBeVisible();
});

test('Digital Akte keeps its own route and back navigation clears record parameters',async({page})=>{
  await page.goto('/?view=akte&akte_kind=worker&akte_id=worker-akte-1');
  await expect(page).toHaveURL(/view=akte/);
  await expect(page).toHaveURL(/akte_id=worker-akte-1/);
  await expect(page.getByTestId('akte-page')).toBeVisible();

  await page.getByRole('button',{name:'Personal & Kunden'}).click();
  await expect(page).toHaveURL(/view=people/);
  await expect(page).not.toHaveURL(/akte_id=/);
});

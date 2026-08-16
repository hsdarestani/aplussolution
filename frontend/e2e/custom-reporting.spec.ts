import { expect, Page, Route, test } from '@playwright/test';

const admin={id:'admin-report',email:'admin@example.test',name:'Alex Admin',first_name:'Alex',last_name:'Admin',role:'admin',phone:'',capabilities:['reports.view','reports.manage','wage.view']};
const viewer={id:'manager-report',email:'manager@example.test',name:'Mina Manager',first_name:'Mina',last_name:'Manager',role:'manager',phone:'',capabilities:['manager.access','reports.view','schedule.view']};
const sources=[
  {key:'shifts',label:'Schichten',default_columns:['date','employee_name','location'],fields:[{key:'date',label:'Datum',wage:false},{key:'employee_name',label:'Mitarbeiter',wage:false},{key:'location',label:'Einsatzort',wage:false},{key:'scheduled_minutes',label:'Plan-Minuten',wage:false},{key:'hourly_rate',label:'Stundenlohn',wage:true},{key:'scheduled_cost',label:'Geplante Kosten',wage:true}]},
  {key:'labor',label:'Personalkosten',default_columns:['employee_name','location','scheduled_minutes','actual_minutes','variance_minutes'],fields:[{key:'employee_name',label:'Mitarbeiter',wage:false},{key:'location',label:'Einsatzort',wage:false},{key:'scheduled_minutes',label:'Plan-Minuten',wage:false},{key:'actual_minutes',label:'Ist-Minuten',wage:false},{key:'variance_minutes',label:'Abweichung (Min.)',wage:false},{key:'scheduled_cost',label:'Plan-Kosten',wage:true},{key:'actual_cost',label:'Ist-Kosten',wage:true}]},
];
async function json(route:Route,body:any,status=200){await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});}

async function mock(page:Page,user:any){
  let definitions:any[]=[];let schedules:any[]=[];let runs:any[]=[];
  await page.addInitScript(()=>{localStorage.setItem('access','reports-e2e');localStorage.setItem('refresh','reports-refresh');});
  await page.route('**/api/**',async route=>{
    const req=route.request();const path=new URL(req.url()).pathname.replace(/^\/api\//,'');
    if(path==='auth/me/')return json(route,user);
    if(path==='reports/builder/catalog/'){
      const canManage=user.role==='admin'||user.capabilities.includes('reports.manage');
      const allowed=sources.map(source=>({...source,fields:source.fields.filter(field=>!field.wage||user.capabilities.includes('wage.view'))}));
      return json(route,{sources:allowed,can_manage:canManage,formats:[{key:'csv',label:'CSV'},{key:'xlsx',label:'Excel XLSX'}],frequencies:[{key:'daily',label:'Täglich'},{key:'weekly',label:'Wöchentlich'},{key:'monthly',label:'Monatlich'}]});
    }
    if(path==='reports/builder/options/')return json(route,{workers:[{id:'worker-1',number:'MA-001',name:'Anna Becker'}],locations:[{id:'loc-1',name:'Messe Frankfurt'}],positions:[{id:'pos-1',name:'Servicekraft'}],schedules:[{id:'schedule-1',name:'Frankfurt'}]});
    if(path==='reports/builder/definitions/'&&req.method()==='GET')return json(route,{results:definitions});
    if(path==='reports/builder/definitions/'&&req.method()==='POST'){const body=req.postDataJSON();const row={id:'report-1',...body,created_by:user.id,created_by_name:user.name,last_run_at:null,created_at:new Date().toISOString()};definitions=[row];return json(route,row,201);}
    if(path==='reports/builder/preview/'&&req.method()==='POST'){const body=req.postDataJSON();const columns=(body.columns||[]).map((key:string)=>({key,label:sources.flatMap(x=>x.fields).find(x=>x.key===key)?.label||key}));return json(route,{source:body.data_source,columns,rows:[Object.fromEntries((body.columns||[]).map((key:string)=>[key,key==='employee_name'?'Anna Becker':key==='location'?'Messe Frankfurt':key==='date'?'2026-08-16':240]))],total_rows:1,filters:body.filters});}
    if(path==='reports/builder/schedules/'&&req.method()==='GET')return json(route,{results:schedules});
    if(path==='reports/builder/schedules/'&&req.method()==='POST'){const body=req.postDataJSON();const row={id:'schedule-1',...body,report_name:'Wochenreport',next_run_at:'2026-08-17T08:00:00Z',last_run_at:null,created_by:user.id};schedules=[row];return json(route,row,201);}
    if(path==='reports/builder/runs/')return json(route,{results:runs});
    if(path==='reports/builder/definitions/report-1/run/'&&req.method()==='POST'){runs=[{id:'run-1',report:'report-1',report_name:'Wochenreport',trigger:'manual',file_format:req.postDataJSON().file_format,status:'success',row_count:1,checksum:'abcdef0123456789',created_at:new Date().toISOString()}];await route.fulfill({status:200,contentType:req.postDataJSON().file_format==='csv'?'text/csv':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',body:'report-data'});return;}
    if(path==='operations/')return json(route,{conflicts:[],unavailable_assignments:[],coverage_gaps:[],overtime_risks:[],swaps:[],swap_candidates:[],notifications:[],pending_swaps:0,unapproved_time_entries:0,contracts_due_30:0,estimated_monthly_labor_cost:0,readiness:{}});
    if(path==='operations/folders/')return json(route,{workers:[],clients:[]});
    if(path==='shifts/'||path.startsWith('shifts/?'))return json(route,{results:[]});
    if(path==='integrations/wiw/status/')return json(route,{});
    if(path==='document-catalog/')return json(route,{documents:[]});
    if(path==='automation/orders/packages/')return json(route,{results:[]});
    if(path==='working-time/settings/')return json(route,{employees:[]});
    if(path==='working-time/records/')return json(route,{results:[]});
    if(path==='communications/snapshot/')return json(route,{unread_notifications:0,unread_chat:0,channels:[],notifications:[],settings:{}});
    if(path==='notification-preferences/')return json(route,{results:[]});
    if(path==='conversations/')return json(route,{results:[]});
    if(path==='dashboard/')return json(route,{});
    return json(route,[]);
  });
}

test('admin builds, saves, exports and schedules a custom report',async({page})=>{
  await page.setViewportSize({width:1440,height:1000});await mock(page,admin);await page.goto('/?view=operations');
  await page.getByRole('button',{name:'Berichte öffnen'}).click();
  const panel=page.getByTestId('custom-reporting-panel');await expect(panel).toBeVisible();await expect(panel.getByRole('heading',{name:'Report Builder'})).toBeVisible();
  await expect(panel.getByText('Stundenlohn',{exact:true})).toBeVisible();
  await panel.getByRole('button',{name:'Vorschau erstellen'}).click();
  await expect(panel.getByText('Anna Becker',{exact:true})).toBeVisible();
  await panel.locator('ion-input').filter({hasText:'Berichtsname'}).locator('input').fill('Wochenreport');
  await panel.getByRole('button',{name:'Bericht speichern'}).click();
  await expect(panel.getByText('Wochenreport',{exact:true})).toBeVisible();
  const reportRow=panel.locator('.reporting-list article').filter({hasText:'Wochenreport'});
  await reportRow.getByRole('button',{name:'CSV'}).click();
  await panel.locator('ion-segment-button[value="schedules"]').click();
  await panel.locator('ion-select').filter({hasText:'Bericht'}).click();
  await page.getByRole('radio',{name:'Wochenreport'}).click();
  await panel.locator('ion-input').filter({hasText:'Empfänger'}).locator('input').fill('ops@example.com');
  await panel.getByRole('button',{name:'Versand speichern'}).click();
  await expect(panel.getByText(/ops@example.com/)).toBeVisible();
});

test('report viewer cannot see wage fields or scheduling controls',async({page})=>{
  await page.setViewportSize({width:390,height:844});await mock(page,viewer);await page.goto('/?view=operations');
  await page.getByRole('button',{name:'Berichte öffnen'}).click();
  const panel=page.getByTestId('custom-reporting-panel');await expect(panel).toBeVisible();
  await expect(panel.getByText('Stundenlohn',{exact:true})).toHaveCount(0);
  await expect(panel.getByText('Geplante Kosten',{exact:true})).toHaveCount(0);
  await expect(panel.locator('ion-segment-button[value="schedules"]')).toHaveCount(0);
  await expect(panel.getByText('Für andere Report-Nutzer teilen',{exact:true})).toHaveCount(0);
});

import { expect, Page, Route, test } from '@playwright/test';

const admin={id:'admin-final',email:'admin@example.test',name:'Alex Admin',first_name:'Alex',last_name:'Admin',role:'admin',phone:'',capabilities:['attendance.view','attendance.edit','reports.view']};

async function json(route:Route,body:any,status=200){await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});}

async function mockFinalAttendance(page:Page){
  let policy:any={id:'policy-final',name:'Frankfurt Policy',location:'loc-final',location_name:'Frankfurt',active:true,priority:100,computer_ip_mode:'off',allowed_ip_networks:[],clock_in_location_mode:'block',clock_out_location_mode:'block'};
  let terminals:any[]=[];
  let notices:any[]=[{id:'notice-final',worker:'worker-final',worker_name:'Anna Becker',shift:'shift-final',shift_title:'Servicekraft',location_name:'Frankfurt',notice_type:'missed_clock_in',severity:'warning',status:'open',detected_at:'2026-08-16T08:30:00Z',value_minutes:18,details:{lifecycle:'in_progress'}}];
  await page.addInitScript(()=>{localStorage.setItem('access','attendance-final-e2e');localStorage.setItem('refresh','attendance-final-refresh');});
  await page.route('**/api/**',async route=>{
    const req=route.request();const path=new URL(req.url()).pathname.replace(/^\/api\//,'');
    if(path==='auth/me/')return json(route,admin);
    if(path==='attendance/exceptions/')return json(route,{notice_window_days:7,counts:{attendance_notices:notices.length,critical_notices:0,pending_corrections:0,unapproved_entries:0,long_running_entries:0,total:notices.length},notices,pending_corrections:[],unapproved_entries:[],long_running_entries:[],policies:[policy],terminals});
    if(path==='attendance-policies/'&&req.method()==='GET')return json(route,{results:[policy]});
    if(path==='attendance-policies/policy-final/'&&req.method()==='PATCH'){policy={...policy,...req.postDataJSON()};return json(route,policy);}
    if(path==='attendance-terminals/'&&req.method()==='GET')return json(route,{results:terminals});
    if(path==='attendance-terminals/'&&req.method()==='POST'){
      const body=req.postDataJSON();const row={id:'terminal-final',public_id:'11111111-1111-1111-1111-111111111111',name:body.name,scope_mode:body.scope_mode,scope_label:'Alle Einsatzpläne',location:null,location_name:'Alle Einsatzpläne',active:true,photo_clock_in:false,photo_clock_out:false,last_seen_at:null,terminal_token:'secret-final'};terminals=[row];return json(route,row,201);
    }
    if(path==='attendance-notices/clear-recent/'&&req.method()==='POST'){const count=notices.length;notices=[];return json(route,{cleared:count,window_days:7});}
    if(path==='attendance-notices/notice-final/remind/'&&req.method()==='POST')return json(route,{sent:true});
    if(path==='attendance-notices/notice-final/report-absence/'&&req.method()==='POST')return json(route,{id:'absence-final',status:'coverage_pending',existing:false},201);
    if(path==='locations/')return json(route,{results:[{id:'loc-final',name:'Frankfurt',address:'Messeplatz 1'}]});
    if(path==='communications/snapshot/')return json(route,{unread_notifications:0,unread_chat:0,settings:{}});
    if(path==='notification-preferences/')return json(route,{results:[]});
    if(path==='conversations/')return json(route,{results:[]});
    if(path==='self-service/snapshot/')return json(route,{settings:{},preference:{},time_off_types:[],coverage_pending:0,open_shift_requests_pending:0});
    if(path.startsWith('self-service/'))return json(route,{results:[],workers:[]});
    if(path==='reports/builder/catalog/')return json(route,{sources:[],can_manage:true});
    if(path.startsWith('reports/builder/'))return json(route,{results:[]});
    if(path==='dashboard/')return json(route,{});
    if(path==='time-off/')return json(route,[]);
    if(path==='integrations/wiw/status/')return json(route,{});
    if(path==='document-catalog/')return json(route,{documents:[]});
    if(path==='operations/')return json(route,{conflicts:[],unavailable_assignments:[],coverage_gaps:[],overtime_risks:[],swaps:[],swap_candidates:[],notifications:[],pending_swaps:0,unapproved_time_entries:0,contracts_due_30:0,estimated_monthly_labor_cost:0,readiness:{}});
    if(path==='operations/folders/')return json(route,{workers:[],clients:[]});
    if(['workers/','clients/','positions/','orders/'].includes(path))return json(route,{results:[]});
    return json(route,[]);
  });
}

test('admin closes final attendance gaps from one workspace',async({page})=>{
  await page.setViewportSize({width:1440,height:960});await mockFinalAttendance(page);await page.goto('/');
  await page.getByTestId('attendance-final-launcher').click();
  const panel=page.getByTestId('attendance-final-panel');await expect(panel).toBeVisible();
  await expect(panel.getByRole('heading',{name:'Time & Attendance vollständig steuern'})).toBeVisible();
  await expect(panel.getByText('Attendance Notices der letzten 7 Tage')).toBeVisible();
  await expect(panel.getByText('Anna Becker')).toBeVisible();
  await panel.getByRole('button',{name:'Erinnern'}).click();
  await expect(panel.getByText('Erinnerung gesendet.')).toBeVisible();

  await panel.getByRole('button',{name:'IP-Regeln'}).click();
  await panel.getByLabel('IP-Prüfung').selectOption('block');
  await panel.locator('#att-final-ip-list').fill('203.0.113.42\n198.51.100.0/24');
  await panel.getByRole('button',{name:'IP-Regel speichern'}).click();
  await expect(panel.getByText('IP-Regel gespeichert.')).toBeVisible();
  await expect(panel.getByText('Mobile nutzt Standortregeln, Terminals sind davon ausgenommen.')).toBeVisible();

  await panel.getByRole('button',{name:'Terminals'}).click();
  await panel.getByRole('button',{name:'Terminal anlegen'}).click();
  const modal=page.locator('.att-final-modal').filter({hasText:'Terminal anlegen'});
  await modal.getByLabel('Name').fill('Empfang Tablet');
  await modal.getByLabel('Geltungsbereich').selectOption('all');
  await modal.getByRole('button',{name:'Anlegen'}).click();
  await expect(page.getByText('Terminal Secret',{exact:true})).toBeVisible();
  await expect(page.getByText('secret-final',{exact:true})).toBeVisible();
});

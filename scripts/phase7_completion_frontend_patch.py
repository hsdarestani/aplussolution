from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'Missing expected marker in {path}: {old[:140]!r}')
    target.write_text(text.replace(old, new, 1), encoding='utf-8')


schedule = 'frontend/src/ScheduleV2.tsx'
replace_once(
    schedule,
    "import { akteHref, openAkte, AkteKind } from './entityNavigation';\n",
    "import { akteHref, openAkte, AkteKind } from './entityNavigation';\nimport { enrichLocationPayload } from './locationPicker';\n",
)

replace_once(
    schedule,
    '''function FriendlyDateTime({label,value,onChange}:{label:string;value?:string;onChange:(next:string)=>void}) {
  const parts=splitDateTime(value);
  const setDate=(date:string)=>onChange(joinDateTime(date,parts.time||'09:00'));
  const setTime=(time:string)=>onChange(joinDateTime(parts.date||berlinDate(),time));
  return <div className="sv2-datetime" data-testid={`datetime-${label.toLowerCase()}`}>
    <div className="sv2-datetime-head"><b>{label} *</b><div className="sv2-date-shortcuts"><IonButton size="small" fill="clear" onClick={()=>setDate(berlinDate())}>Heute</IonButton><IonButton size="small" fill="clear" onClick={()=>setDate(berlinDate(1))}>Morgen</IonButton></div></div>
    <div className="sv2-datetime-fields"><IonInput aria-label={`${label} Datum`} fill="outline" type="date" label="Datum" labelPlacement="floating" value={parts.date} onIonInput={e=>setDate(String(val(e)))}/><IonInput aria-label={`${label} Uhrzeit`} fill="outline" type="time" step="900" label="Uhrzeit" labelPlacement="floating" value={parts.time} onIonInput={e=>setTime(String(val(e)))}/></div>
  </div>;
}
''',
    '''const automaticBreakMinutes=(startsAt?:string,endsAt?:string)=>{if(!startsAt||!endsAt)return 0;const hours=(wallClockMs(endsAt)-wallClockMs(startsAt))/3600000;if(hours>=11)return 60;if(hours>=9)return 45;if(hours>=6)return 30;return 0;};
const NOTE_TEMPLATES:[string,string][]=[
  ['', 'Textvorlage auswählen …'],
  ['uniform','Bitte pünktlich erscheinen und auf vollständige, saubere Arbeitskleidung achten.'],
  ['contact','Bitte 10 Minuten vor Einsatzbeginn vor Ort sein und sich bei der Einsatzleitung melden.'],
  ['documents','Bitte Ausweis und alle für den Einsatz erforderlichen Unterlagen mitbringen.'],
  ['hotel','Bitte gepflegte schwarze Kleidung und schwarze, geschlossene Schuhe tragen.'],
];
const SCHEDULE_GROUPS:[string,string][]=[['service','Service'],['front_office','Front Office'],['housekeeping','Housekeeping']];
const scheduleGroupsForClient=(name?:string)=>/hotel\\s*spenerhaus/i.test(String(name||''))?['front_office','housekeeping']:[];
const scheduleGroupsForPosition=(name?:string)=>/house\\s*keeping/i.test(String(name||''))?['housekeeping']:/front[-\\s]*office/i.test(String(name||''))?['front_office']:/service|bar-support/i.test(String(name||''))?['service']:[];

function FriendlyDateTime({label,value,onChange}:{label:string;value?:string;onChange:(next:string)=>void}) {
  const quick=(offset:number)=>{const date=berlinDate(offset);const time=splitDateTime(value).time||'09:00';onChange(joinDateTime(date,time));};
  return <div className="sv2-datetime" data-testid={`datetime-${label.toLowerCase()}`}>
    <div className="sv2-datetime-head"><b>{label} *</b><div className="sv2-date-shortcuts"><IonButton size="small" fill="clear" onClick={()=>quick(0)}>Heute</IonButton><IonButton size="small" fill="clear" onClick={()=>quick(1)}>Morgen</IonButton></div></div>
    <IonInput aria-label={`${label} Datum und Uhrzeit`} fill="outline" type="datetime-local" step="900" label="Datum & Uhrzeit" labelPlacement="floating" value={value||''} onIonInput={e=>onChange(String(val(e)))}/>
  </div>;
}
''',
)

replace_once(
    schedule,
    "  const [aiOpen,setAiOpen]=useState(false), [orderText,setOrderText]=useState(''), [parsedOrder,setParsedOrder]=useState<any>();\n",
    "  const [aiOpen,setAiOpen]=useState(false), [orderText,setOrderText]=useState(''), [parsedOrder,setParsedOrder]=useState<any>();\n  const [locationOpen,setLocationOpen]=useState(false), [locationForm,setLocationForm]=useState<any>({geofence_radius_m:250});\n",
)

replace_once(
    schedule,
    "  function create(){setEditing(undefined);setForm({required_count:1,break_minutes:0,publish_now:true,confirmation_required:false,workers:[]});setModal(true);}\n  function edit(x:any){setEditing(x.id);setForm({...x,workers:(x.assigned_workers||[]).map((worker:any)=>worker.id),starts_at:x.starts_at?.slice(0,16),ends_at:x.ends_at?.slice(0,16),publish_now:x.status==='published'});setModal(true);}\n  function setShiftDateTime(field:'starts_at'|'ends_at',next:string){setForm((current:any)=>{const updated={...current,[field]:next};if(field==='starts_at'&&next){const start=wallClockMs(next);const currentEnd=current.ends_at?wallClockMs(current.ends_at):undefined;if(!currentEnd||currentEnd<=start)updated.ends_at=fromWallClockMs(start+4*60*60*1000);}return updated;});}\n",
    "  function create(){setEditing(undefined);setForm({required_count:1,break_minutes:0,publish_now:true,confirmation_required:false,workers:[],schedule_groups:[]});setModal(true);}\n  function edit(x:any){setEditing(x.id);setForm({...x,workers:(x.assigned_workers||[]).map((worker:any)=>worker.id),schedule_groups:x.schedule_groups||[],starts_at:x.starts_at?.slice(0,16),ends_at:x.ends_at?.slice(0,16),publish_now:x.status==='published'});setModal(true);}\n  function setShiftDateTime(field:'starts_at'|'ends_at',next:string){setForm((current:any)=>{const updated={...current,[field]:next};if(field==='starts_at'&&next){const start=wallClockMs(next);const currentEnd=current.ends_at?wallClockMs(current.ends_at):undefined;if(!currentEnd||currentEnd<=start)updated.ends_at=fromWallClockMs(start+4*60*60*1000);}updated.break_minutes=automaticBreakMinutes(updated.starts_at,updated.ends_at);return updated;});}\n  async function saveInlineLocation(){if(!form.client){setToast('Bitte zuerst einen Kunden auswählen.');return;}if(!locationForm.name||!locationForm.address){setToast('Bitte Bezeichnung und Adresse eingeben.');return;}setBusy(true);try{const payload=await enrichLocationPayload({...locationForm,client:form.client});const saved:any=await api('locations/',{method:'POST',body:JSON.stringify(payload)});setLocations(current=>[...current.filter(item=>item.id!==saved.id),saved]);setForm((current:any)=>({...current,location:saved.id}));setLocationOpen(false);setLocationForm({geofence_radius_m:250});setToast('Einsatzort gespeichert und ausgewählt.');}catch(e:any){setToast(e.message);}finally{setBusy(false);}}\n",
)

replace_once(
    schedule,
    "      const p:any={client:form.client,location:form.location,position:form.position,starts_at:form.starts_at,ends_at:form.ends_at,break_minutes:Number(form.break_minutes||0),required_count:requiredCount,confirmation_required:!!form.confirmation_required,notes:form.notes||'',status:baseStatus};",
    "      const p:any={client:form.client,location:form.location,position:form.position,starts_at:form.starts_at,ends_at:form.ends_at,break_minutes:automaticBreakMinutes(form.starts_at,form.ends_at),required_count:requiredCount,confirmation_required:!!form.confirmation_required,schedule_groups:form.schedule_groups||[],notes:form.notes||'',status:baseStatus};",
)

replace_once(
    schedule,
    '''      <IonSelect fill="outline" label="Kunde *" labelPlacement="floating" value={form.client} onIonChange={e=>setForm({...form,client:val(e)})}>{clients.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <IonSelect fill="outline" label="Einsatzort *" labelPlacement="floating" value={form.location} onIonChange={e=>setForm({...form,location:val(e)})}>{locations.filter(x=>!form.client||!x.client||x.client===form.client).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <IonSelect fill="outline" label="Position *" labelPlacement="floating" value={form.position} onIonChange={e=>setForm({...form,position:val(e)})}>{positions.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>''',
    '''      <IonSelect fill="outline" label="Kunde *" labelPlacement="floating" value={form.client} onIonChange={e=>{const id=val(e);const selected=clients.find(x=>x.id===id);const groups=scheduleGroupsForClient(selected?.name);setForm({...form,client:id,location:undefined,schedule_groups:groups.length?groups:form.schedule_groups||[]});}}>{clients.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>
      <div className="sv2-location-field"><IonSelect fill="outline" label="Einsatzort *" labelPlacement="floating" value={form.location} disabled={!form.client} onIonChange={e=>setForm({...form,location:val(e)})}>{locations.filter(x=>form.client&&x.client===form.client).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect><IonButton fill="outline" disabled={!form.client} onClick={()=>setLocationOpen(true)}><IonIcon slot="start" icon={addOutline}/>Neu</IonButton></div>
      <IonSelect fill="outline" label="Position *" labelPlacement="floating" value={form.position} onIonChange={e=>{const id=val(e);const position=positions.find(x=>x.id===id);const client=clients.find(x=>x.id===form.client);const clientGroups=scheduleGroupsForClient(client?.name);setForm({...form,position:id,schedule_groups:clientGroups.length?clientGroups:scheduleGroupsForPosition(position?.name)});}}>{positions.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>''',
)

replace_once(
    schedule,
    '''      <FriendlyDateTime label="Beginn" value={form.starts_at} onChange={next=>setShiftDateTime('starts_at',next)}/><FriendlyDateTime label="Ende" value={form.ends_at} onChange={next=>setShiftDateTime('ends_at',next)}/>
      <IonInput fill="outline" type="number" min="1" label="Benötigte Mitarbeiter *" labelPlacement="floating" value={form.required_count} onIonInput={e=>setForm({...form,required_count:Math.max(Number(val(e)||1),(form.workers||[]).length)})}/><IonInput fill="outline" type="number" min="0" label="Pause (Min.)" labelPlacement="floating" value={form.break_minutes} onIonInput={e=>setForm({...form,break_minutes:val(e)})}/>''',
    '''      <FriendlyDateTime label="Beginn" value={form.starts_at} onChange={next=>setShiftDateTime('starts_at',next)}/><FriendlyDateTime label="Ende" value={form.ends_at} onChange={next=>setShiftDateTime('ends_at',next)}/>
      <div className="sv2-staff-stepper" data-testid="required-count-stepper"><span>Benötigte Mitarbeiter *</span><div><button type="button" aria-label="Mitarbeiter reduzieren" disabled={Number(form.required_count||1)<=Math.max(1,(form.workers||[]).length)} onClick={()=>setForm({...form,required_count:Math.max((form.workers||[]).length,Number(form.required_count||1)-1,1)})}>−</button><strong>{form.required_count||1}</strong><button type="button" aria-label="Mitarbeiter erhöhen" onClick={()=>setForm({...form,required_count:Number(form.required_count||1)+1})}>+</button></div></div><div className="sv2-auto-break"><span>Pause automatisch</span><strong>{automaticBreakMinutes(form.starts_at,form.ends_at)} Min.</strong><small>&lt; 6h: 0 · ab 6h: 30 · ab 9h: 45 · ab 11h: 60</small></div>''',
)

replace_once(
    schedule,
    '''      <IonSelect className="full" multiple interface="alert" fill="outline" label="Mitarbeiter direkt zuweisen (optional)" labelPlacement="floating" value={form.workers||[]} onIonChange={e=>{const selected=Array.isArray(val(e))?val(e):[];setForm({...form,workers:selected,required_count:Math.max(Number(form.required_count||1),selected.length)});}}>{workers.map(worker=><IonSelectOption key={worker.id} value={worker.id}>{workerLabel(worker)} · {worker.employee_number}</IonSelectOption>)}</IonSelect>''',
    '''      <IonSelect className="full" multiple interface="alert" fill="outline" label="Mitarbeiter direkt zuweisen (optional)" labelPlacement="floating" value={form.workers||[]} onIonChange={e=>{const selected=Array.isArray(val(e))?val(e):[];const limit=Math.max(1,Number(form.required_count||1));if(selected.length>limit)setToast(`Maximal ${limit} Mitarbeiter auswählbar.`);setForm({...form,workers:selected.slice(0,limit)});}}>{workers.map(worker=><IonSelectOption key={worker.id} value={worker.id}>{workerLabel(worker)} · {worker.employee_number}</IonSelectOption>)}</IonSelect>''',
)

replace_once(
    schedule,
    '''      {(form.workers||[]).length>0&&<div className="full sv2-assignment-note">{(form.workers||[]).length} von {form.required_count||1} Plätzen werden direkt zugewiesen. Freie Restplätze können als OpenShift veröffentlicht werden.</div>}
      <IonTextarea className="full" fill="outline" label="Hinweise für Mitarbeiter" labelPlacement="floating" value={form.notes} onIonInput={e=>setForm({...form,notes:val(e)})}/>''',
    '''      {(form.workers||[]).length>0&&<div className="full sv2-assignment-note">{(form.workers||[]).length} von {form.required_count||1} Plätzen werden direkt zugewiesen. Freie Restplätze können als OpenShift veröffentlicht werden.</div>}
      <IonSelect className="full" multiple interface="alert" fill="outline" label="Zeitplan · Sichtbare Mitarbeitergruppen" labelPlacement="floating" value={form.schedule_groups||[]} onIonChange={e=>setForm({...form,schedule_groups:Array.isArray(val(e))?val(e):[]})}>{SCHEDULE_GROUPS.map(([key,label])=><IonSelectOption key={key} value={key}>{label}</IonSelectOption>)}</IonSelect>
      <IonSelect className="full" fill="outline" label="Textvorlage für Mitarbeiterhinweis" labelPlacement="floating" value="" onIonChange={e=>{const key=String(val(e)||'');const template=NOTE_TEMPLATES.find(([id])=>id===key)?.[1];if(key&&template)setForm({...form,notes:template});}}>{NOTE_TEMPLATES.map(([key,label])=><IonSelectOption key={key||'empty'} value={key}>{label}</IonSelectOption>)}</IonSelect>
      <IonTextarea className="full" fill="outline" label="Hinweise für Mitarbeiter" labelPlacement="floating" value={form.notes} onIonInput={e=>setForm({...form,notes:val(e)})}/>''',
)

ai_marker = '    <IonModal isOpen={aiOpen} onDidDismiss={()=>{setAiOpen(false);setParsedOrder(undefined);}}><div className="sv2-modal" data-testid="schedule-ai-intake">'
replace_once(
    schedule,
    ai_marker,
    '''    <IonModal isOpen={locationOpen} onDidDismiss={()=>setLocationOpen(false)}><div className="sv2-modal"><div className="sv2-modal-head"><h2>Einsatzort anlegen</h2><IonButton fill="clear" onClick={()=>setLocationOpen(false)}>Schließen</IonButton></div><div className="sv2-form"><IonInput fill="outline" label="Bezeichnung *" labelPlacement="floating" value={locationForm.name} onIonInput={e=>setLocationForm({...locationForm,name:val(e)})}/><IonTextarea className="full" fill="outline" label="Adresse *" labelPlacement="floating" value={locationForm.address} onIonInput={e=>setLocationForm({...locationForm,address:val(e)})}/><IonInput fill="outline" type="number" label="Geofence-Radius in Metern" labelPlacement="floating" value={locationForm.geofence_radius_m} onIonInput={e=>setLocationForm({...locationForm,geofence_radius_m:val(e)})}/></div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setLocationOpen(false)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>void saveInlineLocation()}>Speichern</IonButton></div></div></IonModal>

''' + ai_marker,
)

# Global picker: combined date-time and time inputs remain keyboard-editable; date-only selection commits immediately.
replace_once(
    'frontend/src/FriendlyDateTimePicker.tsx',
    "  if (!kind) return;\n  if (isIonInput(element)) enhanceIonInput(element, kind);",
    "  if (!kind) return;\n  if (kind === 'datetime-local' || kind === 'time') return;\n  if (isIonInput(element)) enhanceIonInput(element, kind);",
)
replace_once(
    'frontend/src/FriendlyDateTimePicker.tsx',
    "              onIonChange={(event) => setDraft(String(Array.isArray(event.detail.value) ? event.detail.value[0] || '' : event.detail.value || ''))}",
    "              onIonChange={(event) => { const next=String(Array.isArray(event.detail.value) ? event.detail.value[0] || '' : event.detail.value || ''); if(target.kind==='date'&&next){emitValue(target.element,normalizePickerOutput(target.kind,next));close();}else setDraft(next); }}",
)

# Activate existing geocoder/GPS/Leaflet helper in runtime.
replace_once(
    'frontend/src/main.tsx',
    "import { installOperationalFetchResilience } from './operationalFetchResilience';\n",
    "import { installOperationalFetchResilience } from './operationalFetchResilience';\nimport { installLocationPicker } from './locationPicker';\n",
)
replace_once(
    'frontend/src/main.tsx',
    "installOperationalFetchResilience();\nsetupIonicReact",
    "installOperationalFetchResilience();\ninstallLocationPicker();\nsetupIonicReact",
)

# Persist enriched location coordinates from Settings as well.
replace_once(
    'frontend/src/Settings.tsx',
    "import PortalAccessPanel from './PortalAccessPanel';\n",
    "import PortalAccessPanel from './PortalAccessPanel';\nimport { enrichLocationPayload } from './locationPicker';\n",
)
replace_once(
    'frontend/src/Settings.tsx',
    "  async function submit(path:string,payload:any,done:()=>void){\n    setBusy(true);try{await api(path,{method:'POST',body:JSON.stringify(payload)});done();setModal('');await load();setToast('Einstellung wurde gespeichert.');}catch(e:any){setToast(e.message);}finally{setBusy(false);}\n  }",
    "  async function submit(path:string,payload:any,done:()=>void){\n    setBusy(true);try{const finalPayload=path==='locations/'?await enrichLocationPayload(payload):payload;await api(path,{method:'POST',body:JSON.stringify(finalPayload)});done();setModal('');await load();setToast('Einstellung wurde gespeichert.');}catch(e:any){setToast(e.message);}finally{setBusy(false);}\n  }",
)

# Worker Akte: configure OpenShift clients and Zeitplan groups.
akte = 'frontend/src/AktePage.tsx'
replace_once(
    akte,
    "const text = (value: any) => value == null || value === '' ? '–' : String(value);\n",
    "const text = (value: any) => value == null || value === '' ? '–' : String(value);\nconst unpack = (value:any):any[] => value?.results || value || [];\nconst scheduleGroupOptions:[string,string][]=[['service','Service'],['front_office','Front Office'],['housekeeping','Housekeeping']];\n",
)
replace_once(
    akte,
    "  const [profile, setProfile] = useState<any>({});\n  const [master, setMaster] = useState<any>({});",
    "  const [profile, setProfile] = useState<any>({});\n  const [master, setMaster] = useState<any>({});\n  const [clients,setClients]=useState<any[]>([]);",
)
replace_once(
    akte,
    "          extra_allowance: result.profile?.extra_allowance || 0, ranking_points: result.profile?.ranking_points || 0, active: result.profile?.active !== false,",
    "          extra_allowance: result.profile?.extra_allowance || 0, ranking_points: result.profile?.ranking_points || 0, active: result.profile?.active !== false, open_shift_client_ids: result.profile?.open_shift_client_ids || [], schedule_groups: result.profile?.schedule_groups || [],",
)
replace_once(
    akte,
    "  useEffect(() => { void load(); }, [id, kind]);\n",
    "  useEffect(() => { void load(); }, [id, kind]);\n  useEffect(()=>{if(kind==='worker'&&manager(user))void api('clients/?ordering=name').then(result=>setClients(unpack(result).filter((item:any)=>item.active!==false))).catch(()=>setClients([]));},[kind,user.role]);\n",
)
replace_once(
    akte,
    '''            <IonSelect fill="outline" label="Beschäftigungsart" labelPlacement="floating" value={profile.employment_type} onIonChange={e=>setProfile({...profile,employment_type:e.detail.value})}><IonSelectOption value="minijob">Minijob</IonSelectOption><IonSelectOption value="teilzeit">Teilzeit</IonSelectOption><IonSelectOption value="vollzeit">Vollzeit</IonSelectOption><IonSelectOption value="student">Studentische Aushilfe</IonSelectOption></IonSelect>
''',
    '''            <IonSelect fill="outline" label="Beschäftigungsart" labelPlacement="floating" value={profile.employment_type} onIonChange={e=>setProfile({...profile,employment_type:e.detail.value})}><IonSelectOption value="minijob">Minijob</IonSelectOption><IonSelectOption value="teilzeit">Teilzeit</IonSelectOption><IonSelectOption value="vollzeit">Vollzeit</IonSelectOption><IonSelectOption value="student">Studentische Aushilfe</IonSelectOption></IonSelect>
            <IonSelect multiple interface="alert" fill="outline" label="OpenShifts sichtbar für Kunden" labelPlacement="floating" value={profile.open_shift_client_ids||[]} onIonChange={e=>setProfile({...profile,open_shift_client_ids:Array.isArray(e.detail.value)?e.detail.value:[]})}>{clients.map(client=><IonSelectOption key={client.id} value={client.id}>{client.name}</IonSelectOption>)}</IonSelect>
            <IonSelect multiple interface="alert" fill="outline" label="Zeitplan-Gruppen" labelPlacement="floating" value={profile.schedule_groups||[]} onIonChange={e=>setProfile({...profile,schedule_groups:Array.isArray(e.detail.value)?e.detail.value:[]})}>{scheduleGroupOptions.map(([key,label])=><IonSelectOption key={key} value={key}>{label}</IonSelectOption>)}</IonSelect>
''',
)
replace_once(
    akte,
    "          <div><span>Beschäftigung</span><b>{text(data.profile?.employment_type)}</b></div><div><span>Sollstunden / Monat</span>",
    "          <div><span>Beschäftigung</span><b>{text(data.profile?.employment_type)}</b></div><div><span>OpenShift-Kunden</span><b>{(data.profile?.open_shift_client_ids||[]).length?`${(data.profile.open_shift_client_ids||[]).length} ausgewählt`:'Alle'}</b></div><div><span>Zeitplan</span><b>{(data.profile?.schedule_groups||[]).map((key:string)=>scheduleGroupOptions.find(([id])=>id===key)?.[1]||key).join(', ')||'Alle'}</b></div><div><span>Sollstunden / Monat</span>",
)

# Add UI styling for the new shift controls.
css = Path('frontend/src/schedule-v2.css')
css.write_text(css.read_text(encoding='utf-8') + '''

/* phase7-completion-sweep */
.sv2-location-field{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center}.sv2-location-field ion-button{min-height:54px}
.sv2-staff-stepper,.sv2-auto-break{border:1px solid var(--line,#e4e7ec);border-radius:14px;padding:12px 14px;background:#fff;display:flex;align-items:center;justify-content:space-between;gap:12px}.sv2-staff-stepper>span,.sv2-auto-break>span{font-size:13px;font-weight:700;color:#475467}.sv2-staff-stepper>div{display:flex;align-items:center;gap:12px}.sv2-staff-stepper button{width:48px;height:48px;border-radius:14px;border:1px solid #cdd5df;background:#f8fafc;font-size:30px;line-height:1;cursor:pointer}.sv2-staff-stepper button:disabled{opacity:.35}.sv2-staff-stepper strong{min-width:30px;text-align:center;font-size:22px}.sv2-auto-break{display:grid;grid-template-columns:1fr auto}.sv2-auto-break strong{font-size:20px}.sv2-auto-break small{grid-column:1/-1;color:#667085}
@media(max-width:640px){.sv2-location-field{grid-template-columns:1fr}.sv2-location-field ion-button{margin:0}.sv2-staff-stepper,.sv2-auto-break{min-height:72px}}
''', encoding='utf-8')

# Replace obsolete split-readonly datetime E2E with the requested combined/editable contract.
Path('frontend/e2e/friendly-datetime.spec.ts').write_text('''import { expect, Page, Route, test } from '@playwright/test';

async function fulfill(route: Route, body: unknown, status = 200) { await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) }); }
async function mockAdmin(page: Page) {
  await page.addInitScript(() => { localStorage.setItem('access','friendly-datetime-access'); localStorage.setItem('refresh','friendly-datetime-refresh'); });
  await page.route('**/api/**', async route => {
    const path=new URL(route.request().url()).pathname.replace(/^\\/api\\//,'');
    if(path==='auth/me/') return fulfill(route,{id:'admin-1',email:'admin@example.test',name:'A+ Admin',first_name:'A+',last_name:'Admin',role:'admin',phone:''});
    if(path.startsWith('shifts/')) return fulfill(route,[]);
    if(path.startsWith('clients/')) return fulfill(route,[{id:'client-1',name:'Hotel Spenerhaus',active:true}]);
    if(path.startsWith('locations/')) return fulfill(route,[{id:'location-1',client:'client-1',name:'Hotel Spenerhaus',address:'Frankfurt',active:true}]);
    if(path.startsWith('positions/')) return fulfill(route,[{id:'position-1',name:'Front Office',active:true}]);
    if(path.startsWith('workers/')) return fulfill(route,[]);
    return fulfill(route,[]);
  });
}

test('shift form uses one editable date-time field per boundary and keeps quick date shortcuts', async ({page}) => {
  await page.setViewportSize({width:390,height:844}); await mockAdmin(page); await page.goto('/?view=schedule');
  await page.getByTestId('schedule-create-manual').click();
  const start=page.getByTestId('datetime-beginn'); const end=page.getByTestId('datetime-ende');
  const startField=start.locator('ion-input[type="datetime-local"]'); const endField=end.locator('ion-input[type="datetime-local"]');
  await expect(startField).toBeVisible(); await expect(endField).toBeVisible();
  await expect(start.locator('ion-input')).toHaveCount(1); await expect(end.locator('ion-input')).toHaveCount(1);
  await expect(startField).not.toHaveAttribute('readonly','');
  await startField.evaluate((element:any)=>{element.value='2026-08-28T08:30';element.dispatchEvent(new CustomEvent('ionInput',{detail:{value:'2026-08-28T08:30'},bubbles:true,composed:true}));});
  await expect.poll(()=>startField.evaluate((element:any)=>String(element.value||''))).toContain('2026-08-28T08:30');
  await expect(start.getByRole('button',{name:'Heute'})).toBeVisible(); await expect(start.getByRole('button',{name:'Morgen'})).toBeVisible();
  await expect(page.getByTestId('required-count-stepper')).toBeVisible();
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth); expect(overflow).toBeLessThanOrEqual(1);
});
''', encoding='utf-8')

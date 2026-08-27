from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


def replace_count(text: str, old: str, new: str, expected: int, label: str) -> str:
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f'{label}: expected {expected} matches, found {count}')
    return text.replace(old, new)


def remove_between(text: str, start: str, end: str, label: str) -> str:
    start_i = text.find(start)
    end_i = text.find(end, start_i + len(start))
    if start_i < 0 or end_i < 0:
        raise RuntimeError(f'{label}: markers not found')
    return text[:start_i] + text[end_i:]


# ---------------------------------------------------------------------------
# App shell: remove manager Auftrag & AI navigation, add Einstellungen,
# and keep Personal & Kunden focused on the two profile lists.
# ---------------------------------------------------------------------------
app_path = Path('frontend/src/App.tsx')
app = app_path.read_text()
app = replace_once(app, "  sendOutline,\n  starOutline,", "  sendOutline,\n  settingsOutline,\n  starOutline,", 'settings icon import')
app = replace_once(app, "import PortalAccessPanel from './PortalAccessPanel';\n", '', 'remove PortalAccessPanel import')
app = replace_once(app, "import AktePage from './AktePage';\n", "import AktePage from './AktePage';\nimport Settings from './Settings';\n", 'Settings import')
app = replace_once(app, "  | 'operations'\n  | 'akte';", "  | 'operations'\n  | 'settings'\n  | 'akte';", 'View settings')
app = replace_once(app, "  profile: peopleOutline,\n  operations: refreshOutline,", "  profile: peopleOutline,\n  operations: refreshOutline,\n  settings: settingsOutline,", 'settings icon map')
app = replace_count(
    app,
    "    ['people', 'Personal & Kunden'],\n    ['orders', 'Aufträge & AI'],\n    ['contracts', 'Verträge & ANÜ'],",
    "    ['people', 'Personal & Kunden'],\n    ['settings', 'Einstellungen'],\n    ['contracts', 'Verträge & ANÜ'],",
    2,
    'manager nav cleanup',
)
app = replace_once(
    app,
    "          <IonButton onClick={() => navigate('orders')}><IonIcon slot=\"start\" icon={briefcaseOutline} />Auftrag & AI</IonButton>\n",
    '',
    'dashboard Auftrag action',
)
app = replace_once(
    app,
    '        text="Benutzerkonten, digitale Akten und zentrale Stammdaten."',
    '        text="Mitarbeiter- und Kundenprofile zentral verwalten."',
    'People subtitle',
)
app = replace_once(
    app,
    "              <IonButton fill=\"outline\" onClick={() => setModal('csv')}>\n                CSV-Import\n              </IonButton>\n",
    '',
    'People CSV action',
)
app = replace_once(app, "      {isManager(user) && <PortalAccessPanel />}\n\n", '', 'People portal panel')
app = replace_once(
    app,
    '        count={workers.length + clients.length}',
    '        count={workers.length + clients.filter((client) => client.active).length}',
    'People count active clients',
)
app = replace_once(
    app,
    "          {clients.length ? (\n            clients.map((client) => (",
    "          {clients.filter((client) => client.active).length ? (\n            clients.filter((client) => client.active).map((client) => (",
    'People active client list',
)
app = remove_between(
    app,
    '      <div className="columns master-data">',
    "      <FormModal\n        open={modal === 'worker'}",
    'remove master data UI from People',
)
app = replace_once(
    app,
    "  else if (view === 'people') content = <People user={user} />;\n  else if (view === 'messages')",
    "  else if (view === 'people') content = <People user={user} />;\n  else if (view === 'settings') content = <Settings user={user} />;\n  else if (view === 'messages')",
    'settings route',
)
app = replace_once(
    app,
    "    people: 'Personal',\n    messages: 'Chat',",
    "    people: 'Personal',\n    settings: 'Setup',\n    messages: 'Chat',",
    'mobile settings label',
)
app_path.write_text(app)


# ---------------------------------------------------------------------------
# Schedule V2: remove Auftrag from manual shift creation and surface the existing
# AI intake in Dienstplan as a sibling entry path.
# ---------------------------------------------------------------------------
schedule_path = Path('frontend/src/ScheduleV2.tsx')
schedule = schedule_path.read_text()
schedule = replace_once(
    schedule,
    "import { addOutline, checkmarkCircleOutline, locationOutline, refreshOutline, timeOutline } from 'ionicons/icons';",
    "import { addOutline, briefcaseOutline, checkmarkCircleOutline, locationOutline, refreshOutline, timeOutline } from 'ionicons/icons';",
    'schedule AI icon',
)
schedule = replace_once(
    schedule,
    "  const [rows,setRows]=useState<any[]>([]), [clients,setClients]=useState<any[]>([]), [locations,setLocations]=useState<any[]>([]), [positions,setPositions]=useState<any[]>([]), [orders,setOrders]=useState<any[]>([]), [workers,setWorkers]=useState<any[]>([]);",
    "  const [rows,setRows]=useState<any[]>([]), [clients,setClients]=useState<any[]>([]), [locations,setLocations]=useState<any[]>([]), [positions,setPositions]=useState<any[]>([]), [workers,setWorkers]=useState<any[]>([]);",
    'remove orders state',
)
schedule = replace_once(
    schedule,
    "  const [serviceFilter,setServiceFilter]=useState<ServiceFilter>('all');\n",
    "  const [serviceFilter,setServiceFilter]=useState<ServiceFilter>('all');\n  const [aiOpen,setAiOpen]=useState(false), [orderText,setOrderText]=useState(''), [parsedOrder,setParsedOrder]=useState<any>();\n",
    'AI state',
)
schedule = replace_once(
    schedule,
    "    const [s,c,l,p,o,w]=await Promise.all([api(`shifts/?ordering=starts_at${q}`),api('clients/'),api('locations/'),api('positions/'),api('orders/'),api('workers/?ordering=user__last_name')]);\n    setRows(unpack(s)); setClients(unpack(c)); setLocations(unpack(l)); setPositions(unpack(p)); setOrders(unpack(o)); setWorkers(unpack(w).filter((item:any)=>item.active!==false&&!isSyntheticWorker(item)));",
    "    const [s,c,l,p,w]=await Promise.all([api(`shifts/?ordering=starts_at${q}`),api('clients/'),api('locations/'),api('positions/'),api('workers/?ordering=user__last_name')]);\n    setRows(unpack(s)); setClients(unpack(c).filter((item:any)=>item.active!==false)); setLocations(unpack(l).filter((item:any)=>item.active!==false)); setPositions(unpack(p).filter((item:any)=>item.active!==false)); setWorkers(unpack(w).filter((item:any)=>item.active!==false&&!isSyntheticWorker(item)));",
    'schedule master data load',
)
schedule = replace_once(
    schedule,
    "      const p:any={client:form.client,location:form.location,position:form.position,order:form.order||null,starts_at:form.starts_at,ends_at:form.ends_at,break_minutes:Number(form.break_minutes||0),required_count:requiredCount,notes:form.notes||'',status:baseStatus};",
    "      const p:any={client:form.client,location:form.location,position:form.position,starts_at:form.starts_at,ends_at:form.ends_at,break_minutes:Number(form.break_minutes||0),required_count:requiredCount,notes:form.notes||'',status:baseStatus};",
    'remove order payload',
)
ai_functions = """
  async function parseAiOrder(){
    if(!orderText.trim()){setToast('Bitte zuerst den Text der Kundenanfrage einfügen.');return;}
    setBusy(true);
    try{
      const result:any=await api('automation/orders/parse/',{method:'POST',body:JSON.stringify({text:orderText})});
      setParsedOrder(result);setToast(`${result.shifts?.length||0} Schicht(en) erkannt. Bitte kurz prüfen.`);
    }catch(e:any){setToast(e.message);}finally{setBusy(false);}
  }
  async function approveAiOrder(){
    if(!parsedOrder)return void parseAiOrder();
    setBusy(true);
    try{
      const result:any=await api('automation/orders/approve/',{method:'POST',body:JSON.stringify({parsed:parsedOrder,raw_text:orderText})});
      setAiOpen(false);setOrderText('');setParsedOrder(undefined);await load();setToast(`${result.created_count||0} Personalplatz/-plätze als OpenShift erstellt.`);
    }catch(e:any){setToast(e.message);}finally{setBusy(false);}
  }
"""
schedule = replace_once(
    schedule,
    "  function confirmRelease(){const id=releaseTarget?.id;setReleaseTarget(undefined);if(id) void act(`shifts/${id}/release/`,'Schicht freigegeben.');}",
    ai_functions + "  function confirmRelease(){const id=releaseTarget?.id;setReleaseTarget(undefined);if(id) void act(`shifts/${id}/release/`,'Schicht freigegeben.');}",
    'AI functions',
)
schedule = replace_once(
    schedule,
    "  const searchPlaceholder=clientView?'Einsatz, Ort oder Position suchen …':'Kunde, Ort, Position oder Auftrag suchen …';",
    "  const searchPlaceholder=clientView?'Einsatz, Ort oder Position suchen …':'Kunde, Ort oder Position suchen …';",
    'schedule search placeholder',
)
schedule = replace_once(
    schedule,
    "    <div className=\"sv2-title\"><div><small>{eyebrow}</small><h1>{title}</h1><p>{intro}</p></div>{isManager(user)&&<IonButton onClick={create}><IonIcon slot=\"start\" icon={addOutline}/>Personalbedarf</IonButton>}</div>",
    "    <div className=\"sv2-title\"><div><small>{eyebrow}</small><h1>{title}</h1><p>{intro}</p></div>{isManager(user)&&<div className=\"button-group\"><IonButton data-testid=\"schedule-create-manual\" onClick={create}><IonIcon slot=\"start\" icon={addOutline}/>Manuell</IonButton><IonButton data-testid=\"schedule-create-ai\" fill=\"outline\" onClick={()=>{setParsedOrder(undefined);setOrderText('');setAiOpen(true);}}><IonIcon slot=\"start\" icon={briefcaseOutline}/>AI</IonButton></div>}</div>",
    'manual AI entry actions',
)
schedule = replace_once(
    schedule,
    "      <IonSelect fill=\"outline\" label=\"Auftrag\" labelPlacement=\"floating\" value={form.order} onIonChange={e=>setForm({...form,order:val(e)})}><IonSelectOption value=\"\">Ohne Auftrag</IonSelectOption>{orders.filter(x=>!form.client||x.client===form.client).map(x=><IonSelectOption key={x.id} value={x.id}>{x.title}</IonSelectOption>)}</IonSelect>\n",
    '',
    'remove Auftrag field',
)
ai_modal = """
    <IonModal isOpen={aiOpen} onDidDismiss={()=>{setAiOpen(false);setParsedOrder(undefined);}}><div className="sv2-modal" data-testid="schedule-ai-intake"><div className="sv2-modal-head"><div><small>DIENSTPLAN · AI</small><h2>Personalbedarf mit AI erfassen</h2></div><IonButton fill="clear" onClick={()=>setAiOpen(false)}>Schließen</IonButton></div><div className="sv2-form">
      <IonTextarea className="full" autoGrow fill="outline" label="Text aus Kunden-E-Mail / Anfrage" labelPlacement="floating" value={orderText} onIonInput={e=>{setOrderText(String(val(e)));setParsedOrder(undefined);}}/>
      {parsedOrder&&<div className="full sv2-assignment-note"><b>{parsedOrder.request_id||'Anfrage erkannt'}</b><p>Bitte die erkannten Schichten kurz prüfen:</p>{parsedOrder.shifts?.map((item:any,index:number)=><div key={index}>{item.date} · {item.start_time}–{item.end_time} · {item.count}× {item.role} · {item.site_text||item.location_text}</div>)}</div>}
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setAiOpen(false)}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>void(parsedOrder?approveAiOrder():parseAiOrder())}>{parsedOrder?'Prüfen & OpenShifts erstellen':'Mit AI analysieren'}</IonButton></div></div></IonModal>
"""
schedule = replace_once(
    schedule,
    "    <IonAlert isOpen={!!releaseTarget}",
    ai_modal + "    <IonAlert isOpen={!!releaseTarget}",
    'AI modal',
)
schedule_path.write_text(schedule)


# ---------------------------------------------------------------------------
# New Settings screen with the controls moved out of Personal & Kunden.
# ---------------------------------------------------------------------------
settings = r'''import React, { useEffect, useState } from 'react';
import { IonButton, IonIcon, IonInput, IonModal, IonSelect, IonSelectOption, IonTextarea, IonToast } from '@ionic/react';
import { addOutline, locationOutline, trashOutline } from 'ionicons/icons';
import { api, User } from './api';
import PortalAccessPanel from './PortalAccessPanel';

const unpack=(data:any):any[]=>data?.results||data||[];
const value=(event:any)=>event.detail.value??'';

export default function Settings({user}:{user:User}){
  const [clients,setClients]=useState<any[]>([]),[locations,setLocations]=useState<any[]>([]),[positions,setPositions]=useState<any[]>([]);
  const [modal,setModal]=useState(''),[busy,setBusy]=useState(false),[toast,setToast]=useState('');
  const [locationForm,setLocationForm]=useState<any>({geofence_radius_m:250}),[positionForm,setPositionForm]=useState<any>({color:'#155eef'});
  const [csvFile,setCsvFile]=useState<File>(),[csvType,setCsvType]=useState('workers');

  async function load(){
    const [c,l,p]=await Promise.all([api('clients/?ordering=name'),api('locations/'),api('positions/')]);
    setClients(unpack(c).filter((item:any)=>item.active!==false));
    setLocations(unpack(l).filter((item:any)=>item.active!==false));
    setPositions(unpack(p).filter((item:any)=>item.active!==false));
  }
  useEffect(()=>{void load();},[]);

  async function submit(path:string,payload:any,done:()=>void){
    setBusy(true);try{await api(path,{method:'POST',body:JSON.stringify(payload)});done();setModal('');await load();setToast('Einstellung wurde gespeichert.');}catch(e:any){setToast(e.message);}finally{setBusy(false);}
  }
  async function remove(kind:'locations'|'positions',id:string){
    if(!window.confirm('Diesen Stammdatensatz wirklich löschen?'))return;
    try{await api(`${kind}/${id}/`,{method:'DELETE'});await load();setToast('Datensatz wurde gelöscht.');}catch(e:any){setToast(e.message);}
  }
  async function importCsv(){
    if(!csvFile)return;setBusy(true);const form=new FormData();form.append('file',csvFile);
    try{const result:any=await api(`${csvType}/import_csv/`,{method:'POST',body:form});setToast(`${result.created} Datensätze importiert. ${result.errors?.length||0} Fehler.`);setModal('');setCsvFile(undefined);await load();}catch(e:any){setToast(e.message);}finally{setBusy(false);}
  }

  return <>
    <div className="title"><div><h1>Einstellungen</h1><p>Stammdaten, Portalzugänge und administrative Imports.</p></div><IonButton fill="outline" onClick={()=>setModal('csv')}>CSV-Import</IonButton></div>
    <PortalAccessPanel />
    <div className="columns master-data">
      <div className="panel"><div className="section-head"><div><h3>Einsatzorte</h3><p>Adressen und GPS-Geofences.</p></div><IonButton fill="outline" size="small" onClick={()=>setModal('location')}><IonIcon slot="start" icon={addOutline}/>Standort</IonButton></div>
        {locations.map(location=><div className="row" key={location.id}><IonIcon icon={locationOutline}/><div className="grow"><b>{location.name}</b><p>{location.client_name||'Ohne Kunde'} · {location.address}</p></div><span>{location.geofence_radius_m} m</span><IonButton fill="clear" color="danger" onClick={()=>remove('locations',location.id)}><IonIcon icon={trashOutline}/></IonButton></div>)}
        {!locations.length&&<div className="empty">Noch keine Einsatzorte.</div>}
      </div>
      <div className="panel"><div className="section-head"><div><h3>Positionen</h3><p>Aktive Funktionen für die Dienstplanung.</p></div><IonButton fill="outline" size="small" onClick={()=>setModal('position')}><IonIcon slot="start" icon={addOutline}/>Position</IonButton></div>
        <div className="chips">{positions.map(position=><div className="position-chip" key={position.id}><span style={{background:position.color}}/>{position.name}<button onClick={()=>remove('positions',position.id)} aria-label="Löschen">×</button></div>)}</div>
        {!positions.length&&<div className="empty">Noch keine Positionen.</div>}
      </div>
    </div>

    <IonModal isOpen={modal==='location'} onDidDismiss={()=>setModal('')}><div className="sv2-modal"><div className="sv2-modal-head"><h2>Einsatzort anlegen</h2><IonButton fill="clear" onClick={()=>setModal('')}>Schließen</IonButton></div><div className="sv2-form">
      <IonSelect fill="outline" label="Kunde" labelPlacement="floating" value={locationForm.client} onIonChange={e=>setLocationForm({...locationForm,client:value(e)})}><IonSelectOption value="">Ohne feste Zuordnung</IonSelectOption>{clients.map(client=><IonSelectOption key={client.id} value={client.id}>{client.name}</IonSelectOption>)}</IonSelect>
      <IonInput fill="outline" label="Bezeichnung *" labelPlacement="floating" value={locationForm.name} onIonInput={e=>setLocationForm({...locationForm,name:value(e)})}/>
      <IonTextarea fill="outline" label="Adresse *" labelPlacement="floating" value={locationForm.address} onIonInput={e=>setLocationForm({...locationForm,address:value(e)})}/>
      <IonInput fill="outline" type="number" label="Geofence-Radius in Metern" labelPlacement="floating" value={locationForm.geofence_radius_m} onIonInput={e=>setLocationForm({...locationForm,geofence_radius_m:value(e)})}/>
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setModal('')}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>submit('locations/',{...locationForm,client:locationForm.client||null},()=>setLocationForm({geofence_radius_m:250}))}>Speichern</IonButton></div></div></IonModal>

    <IonModal isOpen={modal==='position'} onDidDismiss={()=>setModal('')}><div className="sv2-modal"><div className="sv2-modal-head"><h2>Position anlegen</h2><IonButton fill="clear" onClick={()=>setModal('')}>Schließen</IonButton></div><div className="sv2-form">
      <IonInput fill="outline" label="Bezeichnung *" labelPlacement="floating" value={positionForm.name} onIonInput={e=>setPositionForm({...positionForm,name:value(e)})}/>
      <IonInput fill="outline" {...({type:'color'} as any)} label="Farbe" labelPlacement="floating" value={positionForm.color} onIonInput={e=>setPositionForm({...positionForm,color:value(e)})}/>
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setModal('')}>Abbrechen</IonButton><IonButton disabled={busy} onClick={()=>submit('positions/',positionForm,()=>setPositionForm({color:'#155eef'}))}>Speichern</IonButton></div></div></IonModal>

    <IonModal isOpen={modal==='csv'} onDidDismiss={()=>setModal('')}><div className="sv2-modal"><div className="sv2-modal-head"><h2>Stammdaten aus CSV importieren</h2><IonButton fill="clear" onClick={()=>setModal('')}>Schließen</IonButton></div><div className="sv2-form">
      <IonSelect fill="outline" label="Datentyp" labelPlacement="floating" value={csvType} onIonChange={e=>setCsvType(String(value(e)))}><IonSelectOption value="workers">Mitarbeiter</IonSelectOption><IonSelectOption value="clients">Kunden</IonSelectOption></IonSelect>
      <label className="file-field full"><span>CSV-Datei auswählen</span><input type="file" accept=".csv,text/csv" onChange={e=>setCsvFile(e.target.files?.[0])}/><b>{csvFile?.name||'Keine Datei ausgewählt'}</b></label>
    </div><div className="sv2-modal-actions"><IonButton fill="outline" onClick={()=>setModal('')}>Abbrechen</IonButton><IonButton disabled={busy||!csvFile} onClick={()=>void importCsv()}>Importieren</IonButton></div></div></IonModal>
    <IonToast isOpen={!!toast} message={toast} duration={3500} onDidDismiss={()=>setToast('')}/>
  </>;
}
'''
Path('frontend/src/Settings.tsx').write_text(settings)


# ---------------------------------------------------------------------------
# Canonical workforce scope + fuzzy typo normalization for new master data.
# ---------------------------------------------------------------------------
scope = r'''import re
import unicodedata
from difflib import SequenceMatcher

CANONICAL_CLIENTS = {
    "Martha's Finest": ("marthas finest", "martha finest", "martha's finest"),
    "City Beach": ("city beach", "citybeach"),
    "OMMIA Frankfurt": ("ommia frankfurt", "ommia", "omnia frankfurt", "omnia"),
    "Messe Frankfurt": ("messe frankfurt", "frankfurter messe"),
    "Stadthaus am Markt": ("stadthaus am markt", "stadhaust am markt"),
    "Hofgut": ("hofgut",),
    "Restaurant Hirschgarten": ("restaurant hirschgarten", "hirschgarten"),
    "Hotel Spenerhaus": ("hotel spenerhaus", "spenerhaus"),
    "Höfel Catering – Aschaffenburg": ("höfel catering aschaffenburg", "hoefel catering aschaffenburg", "hofel catering aschaffenburg", "höfel catering", "hoefel catering"),
}

CANONICAL_POSITIONS = {
    "Servicekraft": ("servicekraft", "servicekrat", "service kraft"),
    "Serviceleitung": ("serviceleitung", "service leitung"),
    "Front Office": ("front office", "front-office", "frontoffice"),
    "Housekeeping": ("housekeeping", "houskeeping", "house keeping"),
    "Bar-Support": ("bar support", "bar-support", "barsupport"),
}


def normalize(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode('ascii').lower().replace('ß', 'ss')
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def _canonical(value, catalog, threshold=0.80):
    needle = normalize(value)
    if not needle:
        return None
    best_name, best_score = None, 0.0
    for canonical, aliases in catalog.items():
        for alias in (canonical, *aliases):
            candidate = normalize(alias)
            if needle == candidate:
                return canonical
            score = SequenceMatcher(None, needle, candidate).ratio()
            if score > best_score:
                best_name, best_score = canonical, score
    return best_name if best_score >= threshold else None


def canonical_client_name(value):
    return _canonical(value, CANONICAL_CLIENTS, 0.78)


def canonical_position_name(value):
    return _canonical(value, CANONICAL_POSITIONS, 0.76)
'''
Path('backend/core/workforce_scope.py').write_text(scope)

views_path=Path('backend/core/views.py')
views=views_path.read_text()
views=replace_once(views, 'from . import oauth\n', 'from . import oauth\nfrom .workforce_scope import canonical_client_name\n', 'scope import in views')
views=replace_once(
    views,
    "    if not name:\n        raise ValueError('Firmenname ist erforderlich.')\n    customer_number = str(data.get('customer_number') or next_number(ClientCompany, 'customer_number', 'KD'))",
    "    if not name:\n        raise ValueError('Firmenname ist erforderlich.')\n    canonical_name = canonical_client_name(name)\n    if canonical_name:\n        name = canonical_name\n        if ClientCompany.objects.filter(name__iexact=name).exists():\n            raise ValueError('Dieser Kunde ist bereits vorhanden.')\n    customer_number = str(data.get('customer_number') or next_number(ClientCompany, 'customer_number', 'KD'))",
    'canonical client onboarding',
)
views_path.write_text(views)

serializers_path=Path('backend/core/serializers.py')
serializers=serializers_path.read_text()
serializers=replace_once(serializers, 'from .models import *\n', 'from .models import *\nfrom .workforce_scope import CANONICAL_POSITIONS, canonical_position_name\n', 'scope serializer import')
serializers=replace_once(
    serializers,
    "class PositionSerializer(serializers.ModelSerializer):\n    class Meta:\n        model = Position\n        fields = '__all__'",
    "class PositionSerializer(serializers.ModelSerializer):\n    class Meta:\n        model = Position\n        fields = '__all__'\n\n    def validate_name(self, value):\n        canonical = canonical_position_name(value)\n        if not canonical:\n            allowed = ', '.join(CANONICAL_POSITIONS)\n            raise serializers.ValidationError(f'Aktuell sind nur diese Positionen vorgesehen: {allowed}.')\n        qs = Position.objects.filter(name__iexact=canonical)\n        if self.instance:\n            qs = qs.exclude(pk=self.instance.pk)\n        if qs.exists():\n            raise serializers.ValidationError('Diese Position ist bereits vorhanden.')\n        return canonical",
    'position canonical validation',
)
serializers_path.write_text(serializers)

bootstrap_path=Path('backend/core/management/commands/bootstrap.py')
bootstrap=bootstrap_path.read_text()
bootstrap=replace_once(
    bootstrap,
    "        for name in ['Servicekraft', 'Hostess', 'Eventhelfer', 'Lagerhelfer', 'Inventurhelfer', 'Promoter', 'Logistiker']:\n            Position.objects.get_or_create(name=name)",
    "        for name in ['Servicekraft', 'Serviceleitung', 'Front Office', 'Housekeeping', 'Bar-Support']:\n            Position.objects.update_or_create(name=name, defaults={'active': True})",
    'bootstrap position scope',
)
bootstrap_path.write_text(bootstrap)

migration = r'''import re
import unicodedata
from difflib import SequenceMatcher

from django.db import migrations

CLIENTS = [
    ("Martha's Finest", ("marthas finest", "martha finest", "martha's finest")),
    ("City Beach", ("city beach", "citybeach")),
    ("OMMIA Frankfurt", ("ommia frankfurt", "ommia", "omnia frankfurt", "omnia")),
    ("Messe Frankfurt", ("messe frankfurt", "frankfurter messe")),
    ("Stadthaus am Markt", ("stadthaus am markt", "stadhaust am markt")),
    ("Hofgut", ("hofgut",)),
    ("Restaurant Hirschgarten", ("restaurant hirschgarten", "hirschgarten")),
    ("Hotel Spenerhaus", ("hotel spenerhaus", "spenerhaus")),
    ("Höfel Catering – Aschaffenburg", ("höfel catering aschaffenburg", "hoefel catering aschaffenburg", "hofel catering aschaffenburg", "höfel catering", "hoefel catering")),
]
POSITIONS = [
    ("Servicekraft", ("servicekraft", "servicekrat", "service kraft"), '#155eef'),
    ("Serviceleitung", ("serviceleitung", "service leitung"), '#7a5af8'),
    ("Front Office", ("front office", "front-office", "frontoffice"), '#0891b2'),
    ("Housekeeping", ("housekeeping", "houskeeping", "house keeping"), '#16a34a'),
    ("Bar-Support", ("bar support", "bar-support", "barsupport"), '#d97706'),
]


def norm(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode('ascii').lower().replace('ß', 'ss')
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def similarity(value, canonical, aliases):
    needle = norm(value)
    scores = [SequenceMatcher(None, needle, norm(item)).ratio() for item in (canonical, *aliases)]
    if needle in {norm(item) for item in (canonical, *aliases)}:
        return 1.0
    return max(scores or [0.0])


def next_customer_number(ClientCompany, index):
    base = f'KD-SCOPE-{index:02d}'
    if not ClientCompany.objects.filter(customer_number=base).exists():
        return base
    suffix = 2
    while ClientCompany.objects.filter(customer_number=f'{base}-{suffix}').exists():
        suffix += 1
    return f'{base}-{suffix}'


def apply_scope(apps, schema_editor):
    ClientCompany = apps.get_model('core', 'ClientCompany')
    Position = apps.get_model('core', 'Position')

    clients = list(ClientCompany.objects.all())
    claimed = set()
    for index, (canonical, aliases) in enumerate(CLIENTS, start=1):
        available = [item for item in clients if item.pk not in claimed]
        exact = [item for item in available if norm(item.name) == norm(canonical)]
        if exact:
            chosen = exact[0]
        else:
            ranked = sorted(((similarity(item.name, canonical, aliases), item) for item in available), key=lambda pair: pair[0], reverse=True)
            chosen = ranked[0][1] if ranked and ranked[0][0] >= 0.78 else None
        if chosen is None:
            chosen = ClientCompany.objects.create(name=canonical, customer_number=next_customer_number(ClientCompany, index), active=True)
            clients.append(chosen)
        else:
            chosen.name = canonical
            chosen.active = True
            chosen.save(update_fields=['name', 'active'])
        claimed.add(chosen.pk)

    ClientCompany.objects.exclude(pk__in=claimed).update(active=False)

    positions = list(Position.objects.all())
    position_claimed = set()
    for canonical, aliases, color in POSITIONS:
        available = [item for item in positions if item.pk not in position_claimed]
        exact = [item for item in available if norm(item.name) == norm(canonical)]
        if exact:
            chosen = exact[0]
        else:
            ranked = sorted(((similarity(item.name, canonical, aliases), item) for item in available), key=lambda pair: pair[0], reverse=True)
            chosen = ranked[0][1] if ranked and ranked[0][0] >= 0.76 else None
        if chosen is None:
            chosen = Position.objects.create(name=canonical, color=color, active=True)
            positions.append(chosen)
        else:
            chosen.name = canonical
            chosen.active = True
            if not chosen.color:
                chosen.color = color
            chosen.save(update_fields=['name', 'active', 'color'])
        position_claimed.add(chosen.pk)

    Position.objects.exclude(pk__in=position_claimed).update(active=False)


class Migration(migrations.Migration):
    dependencies = [('core', '0012_pushdevice')]
    operations = [migrations.RunPython(apply_scope, migrations.RunPython.noop)]
'''
Path('backend/core/migrations/0013_scope_workforce_master_data.py').write_text(migration)

Path('backend/tests/test_workforce_scope.py').write_text(r'''from core.workforce_scope import canonical_client_name, canonical_position_name


def test_known_customer_typos_map_to_canonical_names():
    assert canonical_client_name('ommia fankfurt') == 'OMMIA Frankfurt'
    assert canonical_client_name('stadhaust am markt') == 'Stadthaus am Markt'
    assert canonical_client_name('Hoefel Catering Aschaffenburg') == 'Höfel Catering – Aschaffenburg'


def test_known_position_typos_map_to_canonical_names():
    assert canonical_position_name('Servicekrat') == 'Servicekraft'
    assert canonical_position_name('Houskeeping') == 'Housekeeping'
    assert canonical_position_name('Front-Office') == 'Front Office'
''')


# ---------------------------------------------------------------------------
# E2E coverage for the phase-1 Dienstplan intake structure.
# ---------------------------------------------------------------------------
e2e_path=Path('frontend/e2e/berlin-schedule.spec.ts')
e2e=e2e_path.read_text()
e2e=replace_once(
    e2e,
    "  await expect(page.getByRole('heading', { name: 'Personalbedarf & Schichten' })).toBeVisible();\n",
    "  await expect(page.getByRole('heading', { name: 'Personalbedarf & Schichten' })).toBeVisible();\n  await expect(page.getByTestId('schedule-create-manual')).toBeVisible(); await expect(page.getByTestId('schedule-create-ai')).toBeVisible();\n",
    'schedule entry E2E buttons',
)
extra_test = r'''

test('manager creates workforce demand through Manuell or AI without Auftrag field', async ({ page }) => {
  await page.clock.setFixedTime(fixedNow); await mockAdmin(page); await page.goto('/?view=schedule');
  await page.getByTestId('schedule-create-manual').click();
  await expect(page.getByRole('heading', { name: 'Personalbedarf anlegen' })).toBeVisible();
  await expect(page.getByText('Auftrag', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Schließen' }).click();
  await page.getByTestId('schedule-create-ai').click();
  await expect(page.getByTestId('schedule-ai-intake')).toBeVisible();
  await expect(page.getByText('Personalbedarf mit AI erfassen')).toBeVisible();
});
'''
e2e += extra_test
e2e_path.write_text(e2e)

print('Phase 1 patch applied successfully.')

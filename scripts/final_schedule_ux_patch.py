from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def write(path, content):
    (ROOT / path).write_text(content, encoding='utf-8')


def replace_once(path, old, new):
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected exactly 1 match, got {count}: {old[:90]!r}')
    write(path, text.replace(old, new, 1))


def replace_all(path, old, new, minimum=1):
    text = read(path)
    count = text.count(old)
    if count < minimum:
        raise RuntimeError(f'{path}: expected at least {minimum} matches, got {count}: {old[:90]!r}')
    write(path, text.replace(old, new))


# ---------------------------------------------------------------------------
# Strong, unmistakable customer palette. Each requested customer gets a
# deliberately separated hue so adjacent customer groups remain legible.
# ---------------------------------------------------------------------------
palette = r'''export type SchedulePalette = {
  hue: number;
  accent: string;
  openBackground: string;
  filledBackground: string;
  openText: string;
  filledText: string;
  openMuted: string;
  filledMuted: string;
  legendBackground: string;
  legendText: string;
};

export const normalizeScheduleLabel = (value?: string) =>
  String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/ß/g, 'ss')
    .replace(/[^a-z0-9]/g, '');

export const isHotelClientName = (name?: string) => {
  const key = normalizeScheduleLabel(name);
  return key.includes('spenerhaus') || key.includes('phillippjakobspenerhaus') || key.includes('philippjakobspenerhaus');
};

export const isHotelPositionName = (name?: string) => {
  const key = normalizeScheduleLabel(name);
  return key.includes('housekeeping') || key.includes('houskeeping') || key.includes('frontoffice');
};

function vividPalette(hue: number): SchedulePalette {
  return {
    hue,
    accent: `hsl(${hue} 76% 36%)`,
    openBackground: `linear-gradient(90deg,hsl(${hue} 78% 88%) 0%,hsl(${hue} 70% 95%) 48%,#fff 100%)`,
    filledBackground: `linear-gradient(90deg,hsl(${hue} 72% 28%) 0%,hsl(${hue} 68% 39%) 52%,hsl(${hue} 60% 82%) 100%)`,
    openText: `hsl(${hue} 48% 19%)`,
    filledText: '#ffffff',
    openMuted: `hsl(${hue} 24% 38%)`,
    filledMuted: 'rgba(255,255,255,.88)',
    legendBackground: `hsl(${hue} 70% 91%)`,
    legendText: `hsl(${hue} 62% 25%)`,
  };
}

const blackPalette: SchedulePalette = {
  hue: 0,
  accent: '#111111',
  openBackground: 'linear-gradient(90deg,#d9d9d9 0%,#f2f2f2 52%,#fff 100%)',
  filledBackground: 'linear-gradient(90deg,#050505 0%,#1b1b1b 55%,#606060 100%)',
  openText: '#151515',
  filledText: '#ffffff',
  openMuted: '#5c5c5c',
  filledMuted: '#ededed',
  legendBackground: '#1a1a1a',
  legendText: '#ffffff',
};

const defaultPalette = vividPalette(198);

function customHuePalette(hue: number): SchedulePalette {
  const normalized = ((Math.round(hue) % 360) + 360) % 360;
  return vividPalette(normalized);
}

export function schedulePalette(clientName?: string, _positionName?: string, customHue?: number | null): SchedulePalette {
  if (customHue != null && Number.isFinite(Number(customHue))) return customHuePalette(Number(customHue));
  const client = normalizeScheduleLabel(clientName);

  // Requested operational order is intentionally also reflected in a highly
  // separated color sequence: orange, wine, royal blue, black, green, gold,
  // violet, teal, magenta.
  if (client.includes('martha')) return vividPalette(24);
  if (client.includes('stadthausammarkt') || client.includes('stadhaus')) return vividPalette(350);
  if (isHotelClientName(clientName)) return vividPalette(220);
  if (client.includes('hofelcatering') || client.includes('hofel') || client.includes('hoefel')) return blackPalette;
  if (client.includes('hirschgarten') || client.includes('restauranthirschgarten')) return vividPalette(132);
  if (client.includes('messefrankfurt') || client === 'messe') return vividPalette(46);
  if (client.includes('ommia') || client.includes('omnia')) return vividPalette(282);
  if (client.includes('citybeach')) return vividPalette(184);
  if (client.includes('hofgut')) return vividPalette(320);
  return defaultPalette;
}
'''
write('frontend/src/scheduleClientPalette.ts', palette)


# ---------------------------------------------------------------------------
# Desktop/tablet schedule: customer ordering, one-location auto-selection,
# service filtering, hotel time presets, dividers and editable assignees.
# ---------------------------------------------------------------------------
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "const SCHEDULE_GROUPS:[string,string][]=[['service','Service'],['front_office','Front Office'],['housekeeping','Housekeeping']];\nconst scheduleGroupsForClient=(name?:string)=>/hotel\\s*spenerhaus/i.test(String(name||''))?['front_office','housekeeping']:[];",
    "const SCHEDULE_GROUPS:[string,string][]=[['service','Service'],['front_office','Front Office'],['housekeeping','Housekeeping']];\nconst CLIENT_ORDER=['marthasfinest','stadthausammarkt','hotelspenerhaus','hofelcatering','restauranthirschgarten','messe','ommia','citybeach','hofgut'];\nconst normalizedClient=(name?:string)=>String(name||'').normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().replace(/ß/g,'ss').replace(/[^a-z0-9]/g,'');\nconst clientRank=(name?:string)=>{const key=normalizedClient(name);const index=CLIENT_ORDER.findIndex(item=>key.includes(item)||item.includes(key));return index<0?CLIENT_ORDER.length:index;};\nconst sortClients=(items:any[])=>[...items].sort((a,b)=>clientRank(a?.name)-clientRank(b?.name)||String(a?.name||'').localeCompare(String(b?.name||''),'de'));\nconst scheduleGroupsForClient=(name?:string)=>/hotel\\s*spenerhaus/i.test(String(name||''))?['front_office','housekeeping']:['service'];"
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "setClients(unpack(c).filter(item=>item.active!==false));",
    "setClients(sortClients(unpack(c).filter(item=>item.active!==false)));"
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "const rowsByDay=useMemo(()=>{const map:Record<string,any[]>={}; for(const item of visible){const key=shiftDateKey(item.starts_at);(map[key] ||= []).push(item);} return map;},[visible]);",
    "const rowsByDay=useMemo(()=>{const map:Record<string,any[]>={}; for(const item of visible){const key=shiftDateKey(item.starts_at);(map[key] ||= []).push(item);} Object.values(map).forEach(items=>items.sort((a,b)=>clientRank(a.client_name)-clientRank(b.client_name)||new Date(a.starts_at).getTime()-new Date(b.starts_at).getTime())); return map;},[visible]);"
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "function create(){setEditing(undefined);setForm({required_count:1,break_minutes:0,publish_now:true,confirmation_required:false,workers:[],schedule_groups:[]});setModal(true);}",
    "function create(){setEditing(undefined);setForm({required_count:1,break_minutes:0,publish_now:true,confirmation_required:false,workers:[],schedule_groups:['service']});setModal(true);}"
)
# palette hue is also exposed for E2E and legacy styling compatibility.
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "'--sv2-client-accent':palette.accent,",
    "'--sv2-client-hue':String(palette.hue),\n      '--sv2-client-accent':palette.accent,"
)
# Render a black divider when the next card belongs to another customer.
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "const workerInitials = (worker:any) => String(worker?.name || worker?.employee_number || 'MA').trim().split(/\\s+/).slice(0,2).map((part:string)=>part[0]||'').join('').toUpperCase() || 'MA';",
    "const workerInitials = (worker:any) => String(worker?.name || worker?.employee_number || 'MA').trim().split(/\\s+/).slice(0,2).map((part:string)=>part[0]||'').join('').toUpperCase() || 'MA';\nconst renderCustomerSeparated=(items:any[],render:(item:any)=>React.ReactNode)=>items.map((item,index)=><React.Fragment key={`${item.id}-${index}`}>{index>0&&clientKey(items[index-1])!==clientKey(item)?<div className=\"sv2-client-divider\" aria-hidden=\"true\"/>:null}{render(item)}</React.Fragment>);"
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "{(rowsByDay[anchor]||[]).map(item=>renderMini(item))}",
    "{renderCustomerSeparated(rowsByDay[anchor]||[],item=>renderMini(item))}"
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "{(rowsByDay[key]||[]).map(item=>renderMini(item))}",
    "{renderCustomerSeparated(rowsByDay[key]||[],item=>renderMini(item))}"
)
# Customer selection: apply service default for non-hotel and skip a location
# prompt when the customer has only one active location.
old_customer = "<IonSelect fill=\"outline\" label=\"Kunde *\" labelPlacement=\"floating\" value={form.client} onIonChange={e=>{const id=val(e);const selected=clients.find(x=>x.id===id);const groups=scheduleGroupsForClient(selected?.name);const currentPosition=positions.find(x=>x.id===form.position);setForm({...form,client:id,location:undefined,position:isHotelClientName(selected?.name)&&!isHotelPositionName(currentPosition?.name)?undefined:form.position,schedule_groups:groups.length?groups:form.schedule_groups||[]});}}>{clients.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>"
new_customer = "<IonSelect fill=\"outline\" label=\"Kunde *\" labelPlacement=\"floating\" value={form.client} onIonChange={e=>{const id=val(e);const selected=clients.find(x=>x.id===id);const groups=scheduleGroupsForClient(selected?.name);const currentPosition=positions.find(x=>x.id===form.position);const matchingLocations=locations.filter(x=>x.client===id);const uniqueLocation=matchingLocations.length===1?matchingLocations[0].id:undefined;const serviceOnly=groups.length===1&&groups[0]==='service';setForm({...form,client:id,location:uniqueLocation,position:(isHotelClientName(selected?.name)&&!isHotelPositionName(currentPosition?.name))||(serviceOnly&&isHotelPositionName(currentPosition?.name))?undefined:form.position,schedule_groups:groups});}}>{clients.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>"
replace_once('frontend/src/ScheduleV2.tsx', old_customer, new_customer)

# Position field follows Zeitplan. Service never shows Front Office/Housekeeping.
old_position = "<IonSelect fill=\"outline\" label=\"Position *\" labelPlacement=\"floating\" value={form.position} onIonChange={e=>{const id=val(e);const position=positions.find(x=>x.id===id);const client=clients.find(x=>x.id===form.client);const clientGroups=scheduleGroupsForClient(client?.name);const groups=isHotelClientName(client?.name)?scheduleGroupsForPosition(position?.name):(clientGroups.length?clientGroups:scheduleGroupsForPosition(position?.name));setForm({...form,position:id,schedule_groups:groups});}}>{positions.filter(x=>!isHotelClientName(clients.find(client=>client.id===form.client)?.name)||isHotelPositionName(x.name)).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>"
new_position = "<IonSelect fill=\"outline\" label=\"Position *\" labelPlacement=\"floating\" value={form.position} onIonChange={e=>{const id=val(e);const position=positions.find(x=>x.id===id);const client=clients.find(x=>x.id===form.client);const groups=isHotelClientName(client?.name)?scheduleGroupsForPosition(position?.name):(form.schedule_groups?.length?form.schedule_groups:scheduleGroupsForClient(client?.name));setForm({...form,position:id,schedule_groups:groups});}}>{positions.filter(x=>{const groups=form.schedule_groups||[];if(groups.length===1&&groups[0]==='service')return !isHotelPositionName(x.name);if(groups.includes('front_office')||groups.includes('housekeeping'))return isHotelPositionName(x.name);return true;}).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>"
replace_once('frontend/src/ScheduleV2.tsx', old_position, new_position)

# Hotel time presets. Preserve chosen day and handle night crossing midnight.
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "function FriendlyDateTime({label,value,onChange}:{label:string;value?:string;onChange:(next:string)=>void}) {",
    "function applyHotelPreset(form:any,start:string,end:string,overnight=false){const date=splitDateTime(form.starts_at).date||berlinDate();return {...form,starts_at:joinDateTime(date,start),ends_at:joinDateTime(overnight?addKeyDays(date,1):date,end)};}\n\nfunction FriendlyDateTime({label,value,onChange}:{label:string;value?:string;onChange:(next:string)=>void}) {"
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "<FriendlyDateTime label=\"Beginn\" value={form.starts_at} onChange={next=>setShiftDateTime('starts_at',next)}/><FriendlyDateTime label=\"Ende\" value={form.ends_at} onChange={next=>setShiftDateTime('ends_at',next)}/>",
    "{isHotelClientName(clients.find(client=>client.id===form.client)?.name)&&<div className=\"full sv2-hotel-presets\"><button type=\"button\" onClick={()=>setForm(applyHotelPreset(form,'06:30','15:00'))}>Frühdienst<small>06:30–15:00</small></button><button type=\"button\" onClick={()=>setForm(applyHotelPreset(form,'14:45','22:45'))}>Spätdienst<small>14:45–22:45</small></button><button type=\"button\" onClick={()=>setForm(applyHotelPreset(form,'22:30','06:30',true))}>Nachtdienst<small>22:30–06:30</small></button></div>}<FriendlyDateTime label=\"Beginn\" value={form.starts_at} onChange={next=>setShiftDateTime('starts_at',next)}/><FriendlyDateTime label=\"Ende\" value={form.ends_at} onChange={next=>setShiftDateTime('ends_at',next)}/>"
)
# Employee selector is explicitly editable after creation.
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "label=\"Mitarbeiter direkt zuweisen (optional)\"",
    "label={editing?'Mitarbeiter auswählen / ändern':'Mitarbeiter direkt zuweisen (optional)'}"
)
# Zeitplan service filtering immediately clears an incompatible hotel position.
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "onIonChange={e=>setForm({...form,schedule_groups:Array.isArray(val(e))?val(e):[]})}",
    "onIonChange={e=>{const raw=Array.isArray(val(e))?val(e):[];const groups=raw.includes('service')?['service']:raw;const currentPosition=positions.find(x=>x.id===form.position);setForm({...form,schedule_groups:groups,position:groups.length===1&&groups[0]==='service'&&isHotelPositionName(currentPosition?.name)?undefined:form.position});}}"
)

# CSS additions for desktop/tablet.
with (ROOT/'frontend/src/schedule-v2.css').open('a', encoding='utf-8') as f:
    f.write(r'''

/* Final schedule UX: stronger customer grouping and compact hotel presets */
.sv2-client-divider{grid-column:1/-1;height:2px;min-height:2px;margin:6px 0;background:#111;border-radius:99px;opacity:.9}
.sv2-hotel-presets{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.sv2-hotel-presets button{min-height:52px;padding:8px 6px;border:1px solid #cdd5df;border-radius:10px;background:#f8fafc;color:#173448;font-weight:800;cursor:pointer}
.sv2-hotel-presets small{display:block;margin-top:3px;font-size:10px;font-weight:650;color:#607287}
@media(max-width:700px){.sv2-hotel-presets{grid-template-columns:1fr}.sv2-client-divider{margin:5px 0}}
''')


# ---------------------------------------------------------------------------
# Native/mobile WIW schedule.
# ---------------------------------------------------------------------------
replace_once(
    'frontend/src/WiwScheduleMobile.tsx',
    "const SCHEDULE_GROUPS: Choice[] = [\n  { value: 'service', label: 'Service' },\n  { value: 'front_office', label: 'Front Office' },\n  { value: 'housekeeping', label: 'Housekeeping' },\n];",
    "const SCHEDULE_GROUPS: Choice[] = [\n  { value: 'service', label: 'Service' },\n  { value: 'front_office', label: 'Front Office' },\n  { value: 'housekeeping', label: 'Housekeeping' },\n];\nconst CLIENT_ORDER = ['marthasfinest','stadthausammarkt','hotelspenerhaus','hofelcatering','restauranthirschgarten','messe','ommia','citybeach','hofgut'];\nconst HOTEL_TIME_PRESETS = [\n  { key: 'early', label: 'Frühdienst', start: 6 * 60 + 30, end: 15 * 60 },\n  { key: 'late', label: 'Spätdienst', start: 14 * 60 + 45, end: 22 * 60 + 45 },\n  { key: 'night', label: 'Nachtdienst', start: 22 * 60 + 30, end: 24 * 60 + 6 * 60 + 30 },\n];\nconst clientRank = (name?: string) => { const key = normalize(String(name || '')); const index = CLIENT_ORDER.findIndex((item) => key.includes(item) || item.includes(key)); return index < 0 ? CLIENT_ORDER.length : index; };\nconst sortClients = (items: any[]) => [...items].sort((a, b) => clientRank(a?.name) - clientRank(b?.name) || String(a?.name || '').localeCompare(String(b?.name || ''), 'de'));"
)
replace_once(
    'frontend/src/WiwScheduleMobile.tsx',
    "setClients(unpack(clientData).filter((item: any) => item.active !== false));",
    "setClients(sortClients(unpack(clientData).filter((item: any) => item.active !== false)));"
)
# Expose hue for compatibility and testing.
replace_once(
    'frontend/src/WiwScheduleMobile.tsx',
    "'--wiw-card-accent': palette.accent,",
    "'--wiw-client-hue': String(palette.hue),\n      '--wiw-card-accent': palette.accent,"
)
# Requested customer order within every day.
old_sort = """      const firstStartByClient = new Map<string, number>();
      dayCards.forEach((card) => {
        const key = clientKey(card.shift);
        const start = new Date(card.shift.starts_at).getTime();
        firstStartByClient.set(key, Math.min(firstStartByClient.get(key) ?? Number.POSITIVE_INFINITY, start));
      });
      dayCards.sort((left, right) => {
        const leftKey = clientKey(left.shift);
        const rightKey = clientKey(right.shift);
        const groupOrder = (firstStartByClient.get(leftKey) ?? 0) - (firstStartByClient.get(rightKey) ?? 0);
        if (groupOrder) return groupOrder;
        if (leftKey !== rightKey) return String(left.shift.client_name || '').localeCompare(String(right.shift.client_name || ''), 'de');
        return new Date(left.shift.starts_at).getTime() - new Date(right.shift.starts_at).getTime();
      });"""
new_sort = """      dayCards.sort((left, right) => {
        const groupOrder = clientRank(left.shift.client_name) - clientRank(right.shift.client_name);
        if (groupOrder) return groupOrder;
        const nameOrder = String(left.shift.client_name || '').localeCompare(String(right.shift.client_name || ''), 'de');
        if (nameOrder) return nameOrder;
        return new Date(left.shift.starts_at).getTime() - new Date(right.shift.starts_at).getTime();
      });"""
replace_once('frontend/src/WiwScheduleMobile.tsx', old_sort, new_sort)

# Position choices follow Zeitplan instead of only the customer type.
old_poschoices = """  const positionChoices = useMemo<Choice[]>(() => {
    const hotelOnly = isHotelClientName(clients.find((item: any) => String(item.id) === form.client)?.name);
    return POSITION_ORDER.flatMap((definition) => {
      const match = positions.find((item: any) => definition.aliases.includes(normalize(item.name)));
      if (!match) return [];
      if (hotelOnly && !isHotelPositionName(match.name)) return [];
      return [{ value: String(match.id), label: definition.label }];
    });
  }, [positions, clients, form.client]);"""
new_poschoices = """  const positionChoices = useMemo<Choice[]>(() => {
    const groups = form.schedule_groups || [];
    const serviceOnly = groups.length === 1 && groups[0] === 'service';
    return POSITION_ORDER.flatMap((definition) => {
      const match = positions.find((item: any) => definition.aliases.includes(normalize(item.name)));
      if (!match) return [];
      if (serviceOnly && isHotelPositionName(match.name)) return [];
      if (!serviceOnly && (groups.includes('front_office') || groups.includes('housekeeping')) && !isHotelPositionName(match.name)) return [];
      if (groups.length === 1 && groups[0] === 'front_office' && normalize(match.name) !== 'frontoffice') return [];
      if (groups.length === 1 && groups[0] === 'housekeeping' && !['housekeeping','houskeeping'].includes(normalize(match.name))) return [];
      return [{ value: String(match.id), label: definition.label }];
    });
  }, [positions, form.schedule_groups]);"""
replace_once('frontend/src/WiwScheduleMobile.tsx', old_poschoices, new_poschoices)

# Editing an occupied card must allow changing the employee and persist through
# the real assign endpoint, not only when editing an OpenShift.
old_edit_save = """        if (editing.isOpen && form.workers.length) {
          const targetShiftId = String(edited?.shift?.id || editing.shiftId);
          await api(`shifts/${targetShiftId}/assign/`, {
            method: 'POST',
            body: JSON.stringify({ workers: [form.workers[0]], publish_remaining: form.publish_now }),
          });
          setToast('Mitarbeiter wurde der OpenShift zugewiesen.');
        } else {
          setToast(form.apply_all ? 'Änderungen auf alle Karten angewendet.' : 'Nur diese Schichtkarte wurde geändert.');
        }"""
new_edit_save = """        const targetShiftId = String(edited?.shift?.id || editing.shiftId);
        await api(`shifts/${targetShiftId}/assign/`, {
          method: 'POST',
          body: JSON.stringify({ workers: form.workers.slice(0, 1), publish_remaining: form.publish_now }),
        });
        setToast(form.workers.length ? 'Schicht gespeichert · Mitarbeiterzuweisung aktualisiert.' : 'Schicht gespeichert · als OpenShift freigegeben.');"""
replace_once('frontend/src/WiwScheduleMobile.tsx', old_edit_save, new_edit_save)

# Correct visible create action semantics (also unblocks mobile E2E hook).
replace_once('frontend/src/WiwScheduleMobile.tsx', 'aria-label="Schicht erstellen"', 'aria-label="Schicht anlegen"')

# Card group divider inside a day.
old_cards = """            {dayCards.map((card) => <button type=\"button\" className={`wiw-shift-card ${card.shift.status === 'draft' ? 'is-draft' : card.isOpen ? 'is-open' : 'is-filled'}`} style={shiftCardStyle(card.shift)} key={card.key} onClick={() => card.shift.read_only ? setToast('WIW OpenShift · schreibgeschützt') : openEdit(card)}>
              <div className=\"wiw-card-line primary\"><b>{card.worker?.name || (card.shift.status === 'draft' ? 'Entwurf' : 'OpenShift')}{card.isOpen && card.shift.status !== 'draft' ? <span className=\"wiw-open-alert\">!</span> : null}</b><span>{formatTimeIso(card.shift.starts_at)}–{formatTimeIso(card.shift.ends_at)}</span></div>
              <div className=\"wiw-card-line secondary\"><span className={card.isOpen ? 'open' : ''}>{card.shift.position_name || 'Schicht'}</span><small>{card.shift.location_name || ''}</small></div>
            </button>)}"""
new_cards = """            {dayCards.map((card, index) => <React.Fragment key={card.key}>{index > 0 && clientKey(dayCards[index - 1].shift) !== clientKey(card.shift) ? <div className=\"wiw-client-divider\" aria-hidden=\"true\" /> : null}<button type=\"button\" className={`wiw-shift-card ${card.shift.status === 'draft' ? 'is-draft' : card.isOpen ? 'is-open' : 'is-filled'}`} style={shiftCardStyle(card.shift)} onClick={() => card.shift.read_only ? setToast('WIW OpenShift · schreibgeschützt') : openEdit(card)}>
              <div className=\"wiw-card-line primary\"><b>{card.worker?.name || (card.shift.status === 'draft' ? 'Entwurf' : 'OpenShift')}{card.isOpen && card.shift.status !== 'draft' ? <span className=\"wiw-open-alert\">!</span> : null}</b><span>{formatTimeIso(card.shift.starts_at)}–{formatTimeIso(card.shift.ends_at)}</span></div>
              <div className=\"wiw-card-line secondary\"><span className={card.isOpen ? 'open' : ''}>{card.shift.position_name || 'Schicht'}</span><small>{card.shift.location_name || ''}</small></div>
            </button></React.Fragment>)}"""
replace_once('frontend/src/WiwScheduleMobile.tsx', old_cards, new_cards)

# Hotel time buttons appear as three small presets.
replace_once(
    'frontend/src/WiwScheduleMobile.tsx',
    "          <Row icon={calendarOutline} label={formatDateRow(form.date)} onClick={() => setDateOpen(true)} />\n          <div className=\"wiw-time-row-wrap\">",
    "          <Row icon={calendarOutline} label={formatDateRow(form.date)} onClick={() => setDateOpen(true)} />\n          {isHotelClientName(selectedClientName) ? <div className=\"wiw-hotel-presets\">{HOTEL_TIME_PRESETS.map((preset) => <button type=\"button\" key={preset.key} onClick={() => setForm((current) => ({ ...current, startMinute: preset.start, endAbsolute: preset.end }))}><b>{preset.label}</b><small>{formatMinute(preset.start)}–{formatMinute(preset.end)}</small></button>)}</div> : null}\n          <div className=\"wiw-time-row-wrap\">"
)
# Employee selection is available for every editable card, occupied or open.
old_worker_row = "{(!editing || editing.isOpen) ? <Row icon={peopleOutline} label={editing ? (form.workers.length ? 'Mitarbeiter ändern' : 'Mitarbeiter zuweisen') : (form.workers.length ? `${form.workers.length} Benutzer direkt zugewiesen` : 'Geeignete Benutzer anzeigen')} value={selectedWorkerNames || undefined} emphasizeValue={Boolean(selectedWorkerNames)} muted={!form.workers.length} onClick={() => setSheet('workers')} /> : null}"
new_worker_row = "<Row icon={peopleOutline} label={editing ? (form.workers.length ? 'Mitarbeiter ändern' : 'Mitarbeiter zuweisen') : (form.workers.length ? `${form.workers.length} Benutzer direkt zugewiesen` : 'Geeignete Benutzer anzeigen')} value={selectedWorkerNames || undefined} emphasizeValue={Boolean(selectedWorkerNames)} muted={!form.workers.length} onClick={() => setSheet('workers')} />"
replace_once('frontend/src/WiwScheduleMobile.tsx', old_worker_row, new_worker_row)
# Short copy wording exactly as requested.
replace_once('frontend/src/WiwScheduleMobile.tsx', '<Row icon={copyOutline} label="Schicht als OpenShift kopieren" value="Danach bearbeiten & sichern" onClick={prepareCopyAsOpenShift} />', '<Row icon={copyOutline} label="Schicht kopieren" onClick={prepareCopyAsOpenShift} />')

# Customer sheet: order is already sorted; choose sole location automatically,
# otherwise open location choices. Non-hotel defaults to service.
old_client_sheet = """{sheet === 'client' ? <ChoiceSheet title=\"Kunde\" choices={clientChoices} selected={form.client} onClose={() => setSheet('')} onSelect={(choice) => { const nextName = clients.find((item: any) => String(item.id) === choice.value)?.name; setForm((current) => { const currentPosition = positions.find((item: any) => String(item.id) === current.position); return { ...current, client: choice.value, location: '', position: isHotelClientName(nextName) && !isHotelPositionName(currentPosition?.name) ? '' : current.position }; }); setSheet(''); }} /> : null}"""
new_client_sheet = """{sheet === 'client' ? <ChoiceSheet title=\"Kunde\" choices={clientChoices} selected={form.client} onClose={() => setSheet('')} onSelect={(choice) => { const nextName = clients.find((item: any) => String(item.id) === choice.value)?.name; const matchingLocations = locations.filter((item: any) => String(item.client) === choice.value); const uniqueLocation = matchingLocations.length === 1 ? String(matchingLocations[0].id) : ''; const nextGroups = isHotelClientName(nextName) ? ['front_office', 'housekeeping'] : ['service']; setForm((current) => { const currentPosition = positions.find((item: any) => String(item.id) === current.position); const incompatible = (nextGroups.length === 1 && nextGroups[0] === 'service' && isHotelPositionName(currentPosition?.name)) || (isHotelClientName(nextName) && !isHotelPositionName(currentPosition?.name)); return { ...current, client: choice.value, location: uniqueLocation, position: incompatible ? '' : current.position, schedule_groups: nextGroups }; }); setSheet(matchingLocations.length > 1 ? 'location' : ''); }} /> : null}"""
replace_once('frontend/src/WiwScheduleMobile.tsx', old_client_sheet, new_client_sheet)
# Zeitplan: service is exclusive and clears incompatible positions.
replace_once(
    'frontend/src/WiwScheduleMobile.tsx',
    "{sheet === 'groups' ? <MultiChoiceSheet title=\"Zeitplan\" choices={SCHEDULE_GROUPS} selected={form.schedule_groups} onClose={() => setSheet('')} onChange={(values) => setForm((current) => ({ ...current, schedule_groups: values }))} /> : null}",
    "{sheet === 'groups' ? <MultiChoiceSheet title=\"Zeitplan\" choices={SCHEDULE_GROUPS} selected={form.schedule_groups} onClose={() => setSheet('')} onChange={(values) => setForm((current) => { const groups = values.includes('service') ? ['service'] : values; const currentPosition = positions.find((item: any) => String(item.id) === current.position); return { ...current, schedule_groups: groups, position: groups.length === 1 && groups[0] === 'service' && isHotelPositionName(currentPosition?.name) ? '' : current.position }; })} /> : null}"
)
# Worker sheet works for any edit and changing the worker implies per-card edit.
replace_once(
    'frontend/src/WiwScheduleMobile.tsx',
    "{sheet === 'workers' ? <MultiChoiceSheet title={editing?.isOpen ? 'Mitarbeiter zuweisen' : 'Geeignete Benutzer'} choices={workerChoices} selected={form.workers} limit={editing ? 1 : form.required_count} onClose={() => setSheet('')} onChange={(values) => setForm((current) => ({ ...current, workers: values }))} /> : null}",
    "{sheet === 'workers' ? <MultiChoiceSheet title={editing ? 'Mitarbeiter auswählen / ändern' : 'Geeignete Benutzer'} choices={workerChoices} selected={form.workers} limit={editing ? 1 : form.required_count} onClose={() => setSheet('')} onChange={(values) => setForm((current) => ({ ...current, workers: values, apply_all: editing ? false : current.apply_all }))} /> : null}"
)
# Create defaults to service for the ordinary non-hotel flow.
replace_once('frontend/src/WiwScheduleMobile.tsx', "schedule_groups: [],\n    color_hue: null,", "schedule_groups: ['service'],\n    color_hue: null,")

# Native schedule CSS: more OpenShift/! breathing room, strong black dividers,
# compact hotel presets.
with (ROOT/'frontend/src/wiw-schedule-mobile.css').open('a', encoding='utf-8') as f:
    f.write(r'''

/* Final requested Dienstplan polish */
@media(max-width:900px){
  .wiw-open-alert{margin-left:16px!important}
  .wiw-client-divider{height:3px;background:#111;margin:5px 0;box-shadow:0 1px 0 rgba(255,255,255,.8)}
  .wiw-hotel-presets{padding:8px 10px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;background:#fff;border-bottom:1px solid #dedede}
  .wiw-hotel-presets button{min-width:0;padding:7px 3px;border:1px solid #cfd7df;border-radius:8px;background:#f7f9fb;color:#173448;font:inherit}
  .wiw-hotel-presets b{display:block;font-size:11px;font-weight:850;white-space:nowrap}
  .wiw-hotel-presets small{display:block;margin-top:2px;font-size:8.5px;font-weight:650;color:#697b89;white-space:nowrap}
}
''')

# The old enhancer automatically opened the location sheet after every client
# click. Main form now owns the correct one-location/multi-location behavior.
replace_once(
    'frontend/src/WiwShiftFormUxEnhancer.tsx',
    "function openLocationAfterClientChoice() {\n  window.setTimeout(() => locationRow()?.click(), 90);\n}\n\n",
    ""
)
old_listener = """  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const choiceButton = target?.closest<HTMLButtonElement>('.wiw-choice-sheet > div > button');
      if (!choiceButton) return;
      const sheet = choiceButton.closest('.wiw-choice-sheet');
      const title = text(sheet?.querySelector('header b') || null);
      if (title === 'Kunde') openLocationAfterClientChoice();
    };

    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, []);

"""
replace_once('frontend/src/WiwShiftFormUxEnhancer.tsx', old_listener, '')

# Any other copy labels in frontend are shortened as requested.
for path in (ROOT/'frontend/src').glob('*.tsx'):
    text = path.read_text(encoding='utf-8')
    text = text.replace('Schicht als OpenShift kopieren', 'Schicht kopieren')
    path.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------------------
# Backend: direct admin assignment is authoritative and must never create a
# second confirmation step. Reassignment of an existing occupied shift also
# normalizes the selected slot to confirmed.
# ---------------------------------------------------------------------------
replace_once(
    'backend/core/shift_views.py',
    """                for slot in claimed_slots(obj).select_related('worker__user'):
                    if obj.confirmation_required:
                        slot.confirmation_status = ShiftSlot.ConfirmationStatus.PENDING
                        slot.confirmation_requested_at = now
                        slot.confirmation_decided_at = None
                        Notification.objects.create(
                            user=slot.worker.user,
                            kind=f'shift-confirmation-required-{slot.id}-{int(now.timestamp())}',
                            title='Schicht bestätigen',
                            body=f'{timezone.localtime(obj.starts_at):%d.%m.%Y %H:%M} – {obj.location.name}',
                            action_url='/schedule',
                        )
                    else:
                        slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED
                        slot.confirmation_requested_at = None
                        slot.confirmation_decided_at = now
                    slot.save(update_fields=['confirmation_status', 'confirmation_requested_at', 'confirmation_decided_at', 'updated_at'])""",
    """                accepted_sources = {'admin_assignment', 'worker_claim', 'approved_pickup', 'admin_approved_transfer'}
                for slot in claimed_slots(obj).select_related('worker__user'):
                    requires_confirmation = bool(obj.confirmation_required) and slot.source not in accepted_sources
                    if requires_confirmation:
                        slot.confirmation_status = ShiftSlot.ConfirmationStatus.PENDING
                        slot.confirmation_requested_at = now
                        slot.confirmation_decided_at = None
                        Notification.objects.create(
                            user=slot.worker.user,
                            kind=f'shift-confirmation-required-{slot.id}-{int(now.timestamp())}',
                            title='Schicht bestätigen',
                            body=f'{timezone.localtime(obj.starts_at):%d.%m.%Y %H:%M} – {obj.location.name}',
                            action_url='/schedule',
                        )
                    else:
                        slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED
                        slot.confirmation_requested_at = None
                        slot.confirmation_decided_at = now
                    slot.save(update_fields=['confirmation_status', 'confirmation_requested_at', 'confirmation_decided_at', 'updated_at'])"""
)
replace_once(
    'backend/core/shift_views.py',
    """            desired_ids = {str(worker.pk) for worker in desired_workers}
            for slot in current_slots:""",
    """            desired_ids = {str(worker.pk) for worker in desired_workers}
            now = timezone.now()
            for slot in current_slots:
                if str(slot.worker_id) in desired_ids:
                    slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED
                    slot.confirmation_requested_at = None
                    slot.confirmation_decided_at = now
                    slot.save(update_fields=['confirmation_status', 'confirmation_requested_at', 'confirmation_decided_at', 'updated_at'])
            for slot in current_slots:"""
)
replace_once(
    'backend/core/shift_views.py',
    """                slot.confirmation_status = (
                    ShiftSlot.ConfirmationStatus.PENDING if shift.confirmation_required
                    else ShiftSlot.ConfirmationStatus.CONFIRMED
                )
                slot.confirmation_requested_at = now if shift.confirmation_required else None
                slot.confirmation_decided_at = None if shift.confirmation_required else now""",
    """                slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED
                slot.confirmation_requested_at = None
                slot.confirmation_decided_at = now"""
)
replace_once(
    'backend/core/shift_views.py',
    "'title': 'Schicht bestätigen' if shift.confirmation_required else 'Neue Schicht zugeteilt',",
    "'title': 'Neue Schicht zugeteilt',"
)


# ---------------------------------------------------------------------------
# Splash: slower, intentional reveal + ring pulse + brand/tagline sequencing +
# clean exit. Text remains exactly the already approved two lines.
# ---------------------------------------------------------------------------
replace_once('frontend/src/AppLaunchSplash.tsx', "hide = window.setTimeout(() => setPhase('hide'), 1350);", "hide = window.setTimeout(() => setPhase('hide'), 2050);")
replace_once('frontend/src/AppLaunchSplash.tsx', "      }, 1720);", "      }, 2440);")
replace_once('frontend/src/AppLaunchSplash.tsx', "replay = window.setTimeout(play, 520);", "replay = window.setTimeout(play, 650);")

splash_css = r'''.app-launch-splash{position:fixed;z-index:999999;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;overflow:hidden;background:radial-gradient(circle at 50% 31%,#1b588c 0,#0d355f 31%,#071f3e 67%,#05162c 100%);color:#fff;opacity:1;transform:scale(1);filter:blur(0);transition:opacity .38s ease,transform .38s cubic-bezier(.22,.8,.2,1),filter .38s ease}.app-launch-splash:before{content:'';position:absolute;inset:-25%;background:conic-gradient(from 180deg at 50% 50%,transparent,rgba(231,201,110,.07),transparent 28%,rgba(61,151,220,.08),transparent 62%);animation:aplus-ambient-spin 7s linear infinite}.app-launch-splash.is-hiding{opacity:0;transform:scale(1.035);filter:blur(3px);pointer-events:none}.app-launch-logo-wrap{position:relative;width:min(55vw,224px);height:min(55vw,224px);display:grid;place-items:center;animation:aplus-launch-float 2.1s cubic-bezier(.2,.8,.2,1) both}.app-launch-logo-wrap:after{content:'';position:absolute;z-index:1;inset:23%;border-radius:50%;background:rgba(228,194,95,.15);filter:blur(20px);animation:aplus-core-glow 1.7s ease-out both}.app-launch-logo-wrap img{position:relative;z-index:3;width:78%;max-height:78%;object-fit:contain;filter:drop-shadow(0 14px 31px rgba(0,0,0,.32));animation:aplus-logo-in .82s cubic-bezier(.16,.84,.34,1) both}.app-launch-ring{position:absolute;z-index:2;inset:15%;border:1px solid rgba(231,201,110,.58);border-radius:50%;opacity:0;animation:aplus-ring 1.75s .16s cubic-bezier(.16,.72,.25,1) both}.app-launch-ring.ring-two{inset:4%;border-color:rgba(255,236,167,.34);animation-delay:.42s}.app-launch-splash>strong{position:relative;z-index:3;margin-top:17px;font-size:15px;letter-spacing:.17em;font-weight:780;color:#edd073;opacity:0;animation:aplus-copy-in .58s .58s cubic-bezier(.22,.8,.2,1) forwards}.app-launch-splash>small{position:relative;z-index:3;margin-top:9px;font-size:11.5px;letter-spacing:.12em;font-weight:600;color:rgba(255,255,255,.78);opacity:0;animation:aplus-tagline-in .62s .82s cubic-bezier(.22,.8,.2,1) forwards}.app-launch-progress{position:relative;z-index:3;width:min(42vw,154px);height:2px;margin-top:29px;border-radius:99px;overflow:hidden;background:rgba(255,255,255,.13);opacity:0;animation:aplus-progress-shell .3s .72s forwards}.app-launch-progress i{display:block;width:100%;height:100%;background:linear-gradient(90deg,transparent,#d9b74f 40%,#fff0b8 72%,#fff);transform:translateX(-104%);animation:aplus-progress 1.28s .76s cubic-bezier(.22,.72,.22,1) forwards}.app-launch-glow{position:absolute;border-radius:50%;filter:blur(58px);opacity:.2;will-change:transform}.app-launch-glow-one{width:250px;height:250px;top:10%;left:-120px;background:#2583cb;animation:aplus-glow-one 3.1s ease-in-out infinite alternate}.app-launch-glow-two{width:285px;height:285px;right:-155px;bottom:7%;background:#d0a83e;animation:aplus-glow-two 3.6s ease-in-out infinite alternate}@keyframes aplus-logo-in{0%{opacity:0;transform:scale(.72) translateY(16px);filter:blur(5px)}65%{opacity:1;transform:scale(1.035) translateY(-2px);filter:blur(0)}100%{opacity:1;transform:scale(1) translateY(0);filter:blur(0)}}@keyframes aplus-core-glow{0%{opacity:0;transform:scale(.5)}55%{opacity:1;transform:scale(1.2)}100%{opacity:.62;transform:scale(1)}}@keyframes aplus-ring{0%{opacity:0;transform:scale(.62)}25%{opacity:.72}100%{opacity:0;transform:scale(1.42)}}@keyframes aplus-copy-in{from{opacity:0;transform:translateY(9px);letter-spacing:.24em;filter:blur(3px)}to{opacity:1;transform:translateY(0);letter-spacing:.17em;filter:blur(0)}}@keyframes aplus-tagline-in{from{opacity:0;transform:translateY(7px);letter-spacing:.2em}to{opacity:1;transform:translateY(0);letter-spacing:.12em}}@keyframes aplus-progress-shell{to{opacity:1}}@keyframes aplus-progress{0%{transform:translateX(-104%)}100%{transform:translateX(0)}}@keyframes aplus-launch-float{0%,100%{transform:translateY(0)}52%{transform:translateY(-5px)}}@keyframes aplus-ambient-spin{to{transform:rotate(360deg)}}@keyframes aplus-glow-one{from{transform:translate3d(0,0,0) scale(.9)}to{transform:translate3d(55px,28px,0) scale(1.16)}}@keyframes aplus-glow-two{from{transform:translate3d(0,0,0) scale(.92)}to{transform:translate3d(-48px,-28px,0) scale(1.12)}}@media(prefers-reduced-motion:reduce){.app-launch-splash:before,.app-launch-logo-wrap,.app-launch-logo-wrap:after,.app-launch-logo-wrap img,.app-launch-ring,.app-launch-splash>strong,.app-launch-splash>small,.app-launch-progress,.app-launch-progress i,.app-launch-glow{animation:none!important}.app-launch-splash>strong,.app-launch-splash>small,.app-launch-progress{opacity:1}.app-launch-progress i{transform:none}}
'''
write('frontend/src/app-launch-splash.css', splash_css)

print('final_schedule_ux_patch: OK')

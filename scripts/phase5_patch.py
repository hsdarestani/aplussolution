from pathlib import Path
import re


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, repl: str, label: str) -> str:
    updated, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one regex match, found {count}")
    return updated


Path("frontend/src/entityNavigation.ts").write_text(
    """export type AkteKind = 'worker' | 'client';

export function akteHref(kind: AkteKind, id?: string | null) {
  if (!id) return '#';
  const url = new URL(window.location.href);
  url.searchParams.set('view', 'akte');
  url.searchParams.set('akte_kind', kind);
  url.searchParams.set('akte_id', String(id));
  url.searchParams.delete('people_kind');
  return `${url.pathname}${url.search}`;
}

export function openAkte(kind: AkteKind, id?: string | null) {
  if (!id) return;
  const href = akteHref(kind, id);
  window.history.pushState({ view: 'akte', akte_kind: kind, akte_id: String(id) }, '', href);
  window.dispatchEvent(new PopStateEvent('popstate'));
}
""",
    encoding="utf-8",
)

# Schedule V2: exact Kunde -> Standort -> Mitarbeiter -> Start-Ende -> Profilbild order.
schedule_path = Path("frontend/src/ScheduleV2.tsx")
schedule = schedule_path.read_text(encoding="utf-8")
schedule = replace_once(
    schedule,
    "import { addOutline, briefcaseOutline, checkmarkCircleOutline, locationOutline, refreshOutline, timeOutline } from 'ionicons/icons';",
    "import { addOutline, briefcaseOutline, businessOutline, checkmarkCircleOutline, locationOutline, peopleOutline, personCircleOutline, refreshOutline, timeOutline } from 'ionicons/icons';",
    "schedule icons",
)
schedule = replace_once(
    schedule,
    "import { api, User } from './api';\nimport './schedule-v2.css';",
    "import { api, User } from './api';\nimport { akteHref, openAkte, AkteKind } from './entityNavigation';\nimport './schedule-v2.css';",
    "schedule entity navigation import",
)
renderer = r'''  const renderAkteLink=(kind:AkteKind,id:string|undefined,label:string)=>{
    if(!isManager(user)||!id) return <span>{label}</span>;
    return <a className="sv2-entity-link" href={akteHref(kind,id)} onClick={event=>{event.preventDefault();event.stopPropagation();openAkte(kind,id);}}>{label}</a>;
  };
  const renderWorkerAvatars=(item:any,compact=false)=>{
    const assigned=item.assigned_workers||[];
    if(!assigned.length) return <span className="sv2-no-profile">Noch kein Profilbild</span>;
    const limit=compact?4:8;
    return <div className={`sv2-worker-avatars ${compact?'compact':''}`} aria-label="Profilbilder der zugewiesenen Mitarbeiter">
      {assigned.slice(0,limit).map((worker:any)=>{
        const content=<><span>{workerInitials(worker)}</span>{worker.avatar&&<img src={worker.avatar} alt="" loading="lazy" onError={e=>{e.currentTarget.style.display='none';}}/>}</>;
        return isManager(user)&&worker.id?<a className="sv2-worker-avatar" href={akteHref('worker',worker.id)} key={worker.id||worker.name} title={`${worker.name} · Akte öffnen`} aria-label={`${worker.name} · Akte öffnen`} onClick={event=>{event.preventDefault();event.stopPropagation();openAkte('worker',worker.id);}}>{content}</a>:<span className="sv2-worker-avatar" key={worker.id||worker.name} title={worker.name} aria-label={worker.name}>{content}</span>;
      })}
      {assigned.length>limit&&<span className="sv2-worker-more" title={`${assigned.length-limit} weitere Mitarbeiter`}>+{assigned.length-limit}</span>}
    </div>;
  };
  const renderWorkerNames=(item:any)=>{
    const assigned=item.assigned_workers||[];
    if(!assigned.length) return <span>Noch nicht besetzt</span>;
    return <span className="sv2-worker-names">{assigned.map((worker:any,index:number)=><React.Fragment key={worker.id||worker.name}>{index>0&&<span className="sv2-name-separator">, </span>}{renderAkteLink('worker',worker.id,worker.name||worker.employee_number||'Mitarbeiter')}</React.Fragment>)}</span>;
  };
  const renderShiftDetails=(item:any,compact=false)=><div className={`sv2-event-details ${compact?'compact':''}`} data-testid="shift-card-details">
    <div className="sv2-event-line" data-field="client"><IonIcon icon={businessOutline}/><span className="sv2-field-copy"><small>Kunde</small>{renderAkteLink('client',item.client,item.client_name||'Ohne Kunde')}</span></div>
    <div className="sv2-event-line" data-field="location"><IonIcon icon={locationOutline}/><span className="sv2-field-copy"><small>Standort</small><span>{item.location_name||'Ohne Einsatzort'}</span></span></div>
    <div className="sv2-event-line" data-field="workers"><IonIcon icon={peopleOutline}/><span className="sv2-field-copy"><small>Mitarbeiter</small>{renderWorkerNames(item)}</span></div>
    <div className="sv2-event-line" data-field="time"><IonIcon icon={timeOutline}/><span className="sv2-field-copy"><small>Start–Ende</small><span>{tm(item.starts_at)}–{tm(item.ends_at)}</span></span></div>
    <div className="sv2-event-line sv2-profile-line" data-field="profile"><IonIcon icon={personCircleOutline}/><span className="sv2-field-copy"><small>Profilbild</small>{renderWorkerAvatars(item,compact)}</span></div>
  </div>;
  const renderMini=(item:any,compact=false)=>{const status=statusInfo(item);const canOpen=isManager(user);return <article style={clientStyle(item)} className={`sv2-event ${compact?'compact':''}`} key={item.id} role={canOpen?'button':undefined} tabIndex={canOpen?0:undefined} onClick={()=>openItem(item)} onKeyDown={event=>{if(canOpen&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openItem(item);}}}><div className="sv2-event-head"><strong>{item.position_name||'Einsatz'}</strong><span>{status.label}</span></div>{renderShiftDetails(item,compact)}</article>;};'''
schedule = regex_once(
    schedule,
    r'  const renderWorkerAvatars=.*?  const renderMini=.*?;\n\n(?=  return <div className="sv2">)',
    renderer + "\n\n",
    "schedule shared renderer",
)
old_body = '''      <div className="sv2-body"><small>{renderClientLabel(x)}</small><h3>{x.position_name}</h3><p><IonIcon icon={timeOutline}/> {tm(x.starts_at)}–{tm(x.ends_at)} · {x.break_minutes||0} Min.</p><p><IonIcon icon={locationOutline}/> {x.location_name}</p>{assigned.length>0&&<div className="sv2-list-assignees"><b>Zugewiesen</b>{renderWorkerAvatars(x)}</div>}<div className="sv2-meter"><span style={{width:`${Math.min(100,(Number(x.filled_count||0)/Number(x.required_count||1))*100)}%`}}/></div><em>{x.filled_count||0}/{x.required_count||1} besetzt · {x.open_count||0} frei</em></div>'''
new_body = '''      <div className="sv2-body"><div className="sv2-list-head"><h3>{x.position_name||'Einsatz'}</h3><span>{x.break_minutes||0} Min. Pause</span></div>{renderShiftDetails(x)}<div className="sv2-meter"><span style={{width:`${Math.min(100,(Number(x.filled_count||0)/Number(x.required_count||1))*100)}%`}}/></div><em>{x.filled_count||0}/{x.required_count||1} besetzt · {x.open_count||0} frei</em></div>'''
schedule = replace_once(schedule, old_body, new_body, "schedule list card")
schedule_path.write_text(schedule, encoding="utf-8")

css_path = Path("frontend/src/schedule-v2.css")
css = css_path.read_text(encoding="utf-8")
css += r'''

/* Phase 5 — one semantic shift-card layout in Liste, Tag, Woche, Monat and Einsatzorte. */
.sv2-event{display:block}.sv2-event-head,.sv2-list-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px}.sv2-event-head strong{font-size:12px;line-height:1.25;overflow-wrap:anywhere}.sv2-event-head>span,.sv2-list-head>span{font-size:9px;font-weight:800;color:#667085;background:rgba(255,255,255,.72);border:1px solid rgba(102,112,133,.16);border-radius:999px;padding:2px 6px;white-space:nowrap}.sv2-list-head h3{margin:0}.sv2-event-details{display:grid;gap:5px}.sv2-event-line{display:grid;grid-template-columns:16px minmax(0,1fr);gap:6px;align-items:start;min-width:0;color:#344054}.sv2-event-line>ion-icon{font-size:14px;margin-top:2px;color:hsl(var(--sv2-client-hue,215) 55% 38%)}.sv2-field-copy{display:flex;flex-wrap:wrap;align-items:baseline;gap:3px 6px;min-width:0;font-size:11px;line-height:1.3;overflow-wrap:anywhere}.sv2-field-copy>small{flex:0 0 64px;color:#98a2b3;font-size:8px;font-weight:800;text-transform:uppercase;letter-spacing:.025em}.sv2-entity-link{color:hsl(var(--sv2-client-hue,215) 65% 30%);font-weight:800;text-decoration:none;border-bottom:1px dashed hsl(var(--sv2-client-hue,215) 50% 65%);cursor:pointer}.sv2-entity-link:hover{color:#155eef;border-bottom-style:solid}.sv2-worker-names{min-width:0}.sv2-name-separator{color:#98a2b3}.sv2-profile-line{align-items:center}.sv2-profile-line>ion-icon{margin-top:0}.sv2-profile-line .sv2-field-copy{align-items:center}.sv2-profile-line .sv2-field-copy>small{align-self:center}.sv2-profile-line .sv2-worker-avatars{margin:0}.sv2-no-profile{color:#98a2b3;font-size:10px}.sv2-worker-avatar{color:inherit;text-decoration:none}.sv2-event-details.compact{gap:3px}.sv2-event-details.compact .sv2-event-line{grid-template-columns:12px minmax(0,1fr);gap:3px}.sv2-event-details.compact .sv2-event-line>ion-icon{font-size:10px}.sv2-event-details.compact .sv2-field-copy{font-size:8px;gap:1px 3px}.sv2-event-details.compact .sv2-field-copy>small{flex-basis:43px;font-size:6px}.sv2-event.compact .sv2-event-head{margin-bottom:4px}.sv2-event.compact .sv2-event-head strong{font-size:9px}.sv2-event.compact .sv2-event-head>span{font-size:6px;padding:1px 4px}.sv2-event.compact .sv2-no-profile{font-size:7px}.sv2-single-day-events>.sv2-event{min-height:0}.sv2-body>.sv2-event-details{margin-top:8px}
@media(max-width:700px){.sv2-field-copy>small{flex-basis:58px}.sv2-event-details{gap:6px}.sv2-list-head{align-items:flex-start}.sv2-event.compact .sv2-field-copy>small{flex-basis:40px}}
'''
css_path.write_text(css, encoding="utf-8")

# People filter + direct folder links.
app_path = Path("frontend/src/App.tsx")
app = app_path.read_text(encoding="utf-8")
app = replace_once(
    app,
    "import Settings from './Settings';",
    "import Settings from './Settings';\nimport { akteHref, openAkte } from './entityNavigation';",
    "app entity navigation import",
)
start = app.index("function People({ user }: { user: User }) {")
end = app.index("\nfunction Schedule({ user }:", start)
people = app[start:end]
people = replace_once(
    people,
    "  const [listSort, setListSort] = useState('name');",
    "  const [listSort, setListSort] = useState('name');\n  const [peopleKind, setPeopleKind] = useState<'workers' | 'clients'>(() => new URLSearchParams(window.location.search).get('people_kind') === 'clients' ? 'clients' : 'workers');",
    "people filter state",
)
block_start = people.index("      <ListToolbar\n")
block_end = people.index("      <FormModal\n        open={modal === 'worker'}", block_start)
new_directory = '''      <div className="people-kind-filter" data-testid="people-kind-filter" role="group" aria-label="Akte filtern">
        <button type="button" className={peopleKind === 'workers' ? 'active' : ''} aria-pressed={peopleKind === 'workers'} onClick={() => { setPeopleKind('workers'); const url = new URL(window.location.href); url.searchParams.set('people_kind', 'workers'); window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}`); }}><IonIcon icon={peopleOutline}/>Mitarbeiter <span>{workers.filter((worker) => worker.active).length}</span></button>
        <button type="button" className={peopleKind === 'clients' ? 'active' : ''} aria-pressed={peopleKind === 'clients'} onClick={() => { setPeopleKind('clients'); const url = new URL(window.location.href); url.searchParams.set('people_kind', 'clients'); window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}`); }}><IonIcon icon={businessOutline}/>Kunden <span>{clients.filter((client) => client.active).length}</span></button>
      </div>

      <ListToolbar
        query={listQuery}
        onQuery={setListQuery}
        placeholder={peopleKind === 'workers' ? 'Mitarbeiter suchen …' : 'Kunden suchen …'}
        sort={listSort}
        onSort={setListSort}
        sortOptions={[{ value: 'name', label: 'Nach Name' }, { value: 'number', label: 'Nach Nummer' }]}
        count={peopleKind === 'workers' ? workers.length : clients.filter((client) => client.active).length}
      />

      <div className="columns people-directory-columns">
        {peopleKind === 'workers' ? <div className="panel" data-testid="people-workers-list">
          <div className="section-head"><div><h3>Mitarbeiter</h3><p>{workers.filter((worker) => worker.active).length} aktive Profile</p></div></div>
          {workers.length ? workers.map((worker) => <div className={`row ${worker.active ? '' : 'muted-row'}`} key={worker.id}>
            <div className="avatar">{worker.user_detail?.name?.[0] || 'M'}</div>
            <div className="grow"><a className="entity-name-link" href={akteHref('worker', worker.id)} onClick={(event) => { event.preventDefault(); openAkte('worker', worker.id); }}>{worker.user_detail?.name || worker.user_detail?.email}</a><p>{worker.employee_number} · {worker.employment_type} · {worker.user_detail?.email}</p></div>
            <strong>{worker.ranking_points} P.</strong>
            {isManager(user) && worker.active && <IonButton fill="clear" color="danger" onClick={() => archive('workers', worker.id)}>Deaktivieren</IonButton>}
          </div>) : <Empty>Noch keine Mitarbeiter. Über „Mitarbeiter“ legst du das erste Profil an.</Empty>}
        </div> : <div className="panel" data-testid="people-clients-list">
          <div className="section-head"><div><h3>Kunden</h3><p>{clients.filter((client) => client.active).length} aktive Unternehmen</p></div></div>
          {clients.filter((client) => client.active).length ? clients.filter((client) => client.active).map((client) => <div className="row" key={client.id}>
            <div className="avatar">{client.name?.[0] || 'K'}</div>
            <div className="grow"><a className="entity-name-link" href={akteHref('client', client.id)} onClick={(event) => { event.preventDefault(); openAkte('client', client.id); }}>{client.name}</a><p>{client.customer_number}{client.contacts_detail?.[0]?.email ? ` · ${client.contacts_detail[0].email}` : ''}</p></div>
            {isManager(user) && client.active && <IonButton fill="clear" color="danger" onClick={() => archive('clients', client.id)}>Deaktivieren</IonButton>}
          </div>) : <Empty>Noch keine Kundenunternehmen angelegt.</Empty>}
        </div>}
      </div>

'''
people = people[:block_start] + new_directory + people[block_end:]
app = app[:start] + people + app[end:]
app_path.write_text(app, encoding="utf-8")

people_css = Path("frontend/src/people-lists.css")
pcss = people_css.read_text(encoding="utf-8")
pcss += r'''

/* Phase 5 — explicit digital-file switcher. */
.people-kind-filter{display:inline-flex;gap:4px;padding:4px;margin:0 0 12px;background:#eef3fb;border:1px solid #dce4f2;border-radius:14px}.people-kind-filter button{appearance:none;border:0;background:transparent;color:#475467;display:inline-flex;align-items:center;gap:7px;padding:9px 13px;border-radius:10px;font:700 13px/1.2 inherit;cursor:pointer}.people-kind-filter button.active{background:#fff;color:#155eef;box-shadow:0 1px 5px rgba(15,35,70,.12)}.people-kind-filter button span{min-width:22px;padding:2px 6px;border-radius:999px;background:#e8eef9;color:#475467;font-size:10px}.people-kind-filter button.active span{background:#eaf0ff;color:#155eef}.people-directory-columns{grid-template-columns:minmax(0,1fr)!important}.entity-name-link{display:inline-block;color:#101828;font-weight:800;text-decoration:none;border-bottom:1px dashed #9db1d9}.entity-name-link:hover{color:#155eef;border-bottom-style:solid}@media(max-width:700px){.people-kind-filter{display:flex;width:100%}.people-kind-filter button{flex:1;justify-content:center}}
'''
people_css.write_text(pcss, encoding="utf-8")

akte_path = Path("frontend/src/AktePage.tsx")
akte = akte_path.read_text(encoding="utf-8")
akte = replace_once(
    akte,
    "    const url = new URL(window.location.href); url.searchParams.set('view', 'people'); url.searchParams.delete('akte_kind'); url.searchParams.delete('akte_id');",
    "    const url = new URL(window.location.href); url.searchParams.set('view', 'people'); url.searchParams.set('people_kind', kind === 'client' ? 'clients' : 'workers'); url.searchParams.delete('akte_kind'); url.searchParams.delete('akte_id');",
    "akte back filter",
)
akte_path.write_text(akte, encoding="utf-8")

search_path = Path("frontend/src/GlobalSearch.tsx")
global_search = search_path.read_text(encoding="utf-8")
global_search = replace_once(
    global_search,
    "import { api } from './api';\nimport './global-search.css';",
    "import { api } from './api';\nimport { openAkte } from './entityNavigation';\nimport './global-search.css';",
    "global search entity navigation import",
)
old_select = '''  const select = (result: Result) => {
    sessionStorage.setItem('aplus:focus', JSON.stringify({ view: result.view, id: result.id, type: result.type, query }));
    setOpen(false);
    setQuery('');
    setData(undefined);
    onNavigate(result.view);
  };'''
new_select = '''  const select = (result: Result) => {
    setOpen(false);
    setQuery('');
    setData(undefined);
    if (result.type === 'worker' || result.type === 'client') {
      openAkte(result.type, result.id);
      return;
    }
    sessionStorage.setItem('aplus:focus', JSON.stringify({ view: result.view, id: result.id, type: result.type, query }));
    onNavigate(result.view);
  };'''
global_search = replace_once(global_search, old_select, new_select, "global search direct Akte")
search_path.write_text(global_search, encoding="utf-8")

Path("frontend/e2e/phase5-calendar-navigation.spec.ts").write_text(
    r'''import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('Phase 5 uses the exact shared shift-card information order in every calendar view', async () => {
  const source = readFileSync(resolve(process.cwd(), 'src/ScheduleV2.tsx'), 'utf8');
  const client = source.indexOf('data-field="client"');
  const location = source.indexOf('data-field="location"');
  const workers = source.indexOf('data-field="workers"');
  const time = source.indexOf('data-field="time"');
  const profile = source.indexOf('data-field="profile"');
  expect(client).toBeGreaterThan(-1);
  expect(client).toBeLessThan(location);
  expect(location).toBeLessThan(workers);
  expect(workers).toBeLessThan(time);
  expect(time).toBeLessThan(profile);
  expect(source).toContain('{renderShiftDetails(x)}');
  expect(source).toContain('renderShiftDetails(item,compact)');
  expect(source).toContain("openAkte('client'");
  expect(source).toContain("openAkte('worker'");
});

test('Phase 5 separates Mitarbeiter and Kunden folders and names open digital files', async () => {
  const app = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8');
  const search = readFileSync(resolve(process.cwd(), 'src/GlobalSearch.tsx'), 'utf8');
  const akte = readFileSync(resolve(process.cwd(), 'src/AktePage.tsx'), 'utf8');
  expect(app).toContain('data-testid="people-kind-filter"');
  expect(app).toContain("peopleKind === 'workers'");
  expect(app).toContain("peopleKind === 'clients'");
  expect(app).toContain("akteHref('worker', worker.id)");
  expect(app).toContain("akteHref('client', client.id)");
  expect(search).toContain("result.type === 'worker' || result.type === 'client'");
  expect(search).toContain('openAkte(result.type, result.id)');
  expect(akte).toContain("url.searchParams.set('people_kind', kind === 'client' ? 'clients' : 'workers')");
});
''',
    encoding="utf-8",
)

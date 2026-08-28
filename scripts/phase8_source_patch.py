# Triggered after the helper workflow is present so the patch is atomic.
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'missing marker in {path}: {old[:160]!r}')
    target.write_text(text.replace(old, new, 1), encoding='utf-8')


# App shell: mobile has Dashboard / Dienstplan / Zeiterfassung / Mehr.
replace_once(
    'frontend/src/App.tsx',
    """  const primaryViews: View[] = isManager(user)
    ? ['dashboard', 'schedule', 'time', 'messages']
    : ['dashboard', 'schedule', 'time', 'messages'];""",
    """  const primaryViews: View[] = ['dashboard', 'schedule', 'time'];""",
)
replace_once(
    'frontend/src/App.tsx',
    """    dashboard: 'Start',
    orders: 'Aufträge',
    schedule: 'Dienstplan',
    time: 'Zeit',""",
    """    dashboard: 'Dashboard',
    orders: 'Aufträge',
    schedule: 'Dienstplan',
    time: 'Zeiterfassung',""",
)

# Attendance: workers get the compact WIW Pay Periods mobile screen.
replace_once(
    'frontend/src/AttendanceV3.tsx',
    "import { api, User } from './api';\nimport './attendance-v3.css';",
    "import { api, User } from './api';\nimport Phase8MobileAttendance from './Phase8MobileAttendance';\nimport './attendance-v3.css';",
)
replace_once(
    'frontend/src/AttendanceV3.tsx',
    """  if (!data) return <div className=\"attendance-loading\"><IonSpinner /></div>;

  if (isManager(user)) {""",
    """  if (!data) return <div className=\"attendance-loading\"><IonSpinner /></div>;

  if (user.role === 'worker' && typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches) {
    return <Phase8MobileAttendance data={data} />;
  }

  if (isManager(user)) {""",
)

# Scheduler: mobile opens on day view and receives the WIW week strip, total and FAB.
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "  const [view,setView]=useState<ScheduleView>('list');",
    "  const [view,setView]=useState<ScheduleView>(()=>typeof window!=='undefined'&&window.matchMedia('(max-width: 900px)').matches?'day':'list');",
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    """  const timelineLocations=useMemo(()=>Array.from(new Set(visible.filter(x=>weekDays.includes(shiftDateKey(x.starts_at))).map(x=>x.location_name||'Ohne Einsatzort'))).sort(),[visible,weekDays]);
""",
    """  const timelineLocations=useMemo(()=>Array.from(new Set(visible.filter(x=>weekDays.includes(shiftDateKey(x.starts_at))).map(x=>x.location_name||'Ohne Einsatzort'))).sort(),[visible,weekDays]);
  const weekTotalHours=useMemo(()=>visible.filter(x=>weekDays.includes(shiftDateKey(x.starts_at))).reduce((sum:number,x:any)=>{const gross=Math.max(0,(new Date(x.ends_at).getTime()-new Date(x.starts_at).getTime())/3600000);return sum+Math.max(0,gross-Number(x.break_minutes||0)/60);},0),[visible,weekDays]);
""",
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    """    {workerView?<IonSegment scrollable value={tab} onIonChange={e=>setTab(String(val(e)))}><IonSegmentButton value=\"available\"><IonLabel>Verfügbare Schichten</IonLabel></IonSegmentButton><IonSegmentButton value=\"mine\"><IonLabel>Meine Schichten</IonLabel></IonSegmentButton></IonSegment>:isManager(user)?<IonSegment scrollable value={tab} onIonChange={e=>setTab(String(val(e)))}><IonSegmentButton value=\"open\"><IonLabel>Offen</IonLabel></IonSegmentButton><IonSegmentButton value=\"filled\"><IonLabel>Voll besetzt</IonLabel></IonSegmentButton><IonSegmentButton value=\"draft\"><IonLabel>Entwürfe</IonLabel></IonSegmentButton><IonSegmentButton value=\"all\"><IonLabel>Alle</IonLabel></IonSegmentButton></IonSegment>:null}

    <div className=\"sv2-service-filter\"""",
    """    {workerView?<IonSegment scrollable value={tab} onIonChange={e=>setTab(String(val(e)))}><IonSegmentButton value=\"available\"><IonLabel>Verfügbare Schichten</IonLabel></IonSegmentButton><IonSegmentButton value=\"mine\"><IonLabel>Meine Schichten</IonLabel></IonSegmentButton></IonSegment>:isManager(user)?<IonSegment scrollable value={tab} onIonChange={e=>setTab(String(val(e)))}><IonSegmentButton value=\"open\"><IonLabel>Alle Schichten</IonLabel></IonSegmentButton><IonSegmentButton value=\"filled\"><IonLabel>Voll besetzt</IonLabel></IonSegmentButton><IonSegmentButton value=\"draft\"><IonLabel>Entwürfe</IonLabel></IonSegmentButton><IonSegmentButton value=\"all\"><IonLabel>Alle</IonLabel></IonSegmentButton></IonSegment>:null}

    <div className=\"sv2-wiw-week-strip\" data-testid=\"phase8-week-strip\" aria-label=\"Mobile Wochenwahl\">
      <button type=\"button\" className=\"nav\" aria-label=\"Vorherige Woche\" onClick={()=>setAnchor(addKeyDays(anchor,-7))}>‹</button>
      {weekDays.map(key=><button type=\"button\" key={key} className={`${key===anchor?'active ':''}${key===berlinDate()?'today':''}`} onClick={()=>{setAnchor(key);setView('day');}}><span>{keyLabel(key,{weekday:'short'}).slice(0,1)}</span><b>{keyToDate(key).getUTCDate()}</b></button>)}
      <button type=\"button\" className=\"nav\" aria-label=\"Nächste Woche\" onClick={()=>setAnchor(addKeyDays(anchor,7))}>›</button>
    </div>

    <div className=\"sv2-service-filter\"""",
)
replace_once(
    'frontend/src/ScheduleV2.tsx',
    "\n\n    <IonModal isOpen={modal} onDidDismiss={()=>setModal(false)}>",
    """

    <div className=\"sv2-wiw-total\" data-testid=\"phase8-week-total\"><span>Gesamtstunden</span><strong>{weekTotalHours.toFixed(1)}</strong></div>
    {isManager(user)&&<button type=\"button\" className=\"sv2-wiw-fab\" aria-label=\"Schicht anlegen\" onClick={create}>+</button>}

    <IonModal isOpen={modal} onDidDismiss={()=>setModal(false)}>""",
)

# Admin quick access must not resurrect the removed Auftragseingang & AI area.
replace_once(
    'frontend/src/AdminHomeV4.tsx',
    "  refreshOutline,\n  syncOutline,",
    "  refreshOutline,\n  notificationsOutline,\n  syncOutline,",
)
replace_once(
    'frontend/src/AdminHomeV4.tsx',
    "  { view: 'orders', label: 'Aufträge & AI', hint: 'Anfragen einlesen', icon: briefcaseOutline },",
    "  { view: 'messages', label: 'Mitteilungen', hint: 'Hinweise an Mitarbeiter senden', icon: notificationsOutline },",
)

# Existing mobile regression contract now expects 4 bottom tabs and the full German label.
app_shell = Path('frontend/e2e/app-shell.spec.ts')
text = app_shell.read_text(encoding='utf-8')
text = text.replace("await expect(page.locator('.mobile-tabbar button')).toHaveCount(5);", "await expect(page.locator('.mobile-tabbar button')).toHaveCount(4);")
text = text.replace("filter({ hasText: 'Zeit' })", "filter({ hasText: 'Zeiterfassung' })")
app_shell.write_text(text, encoding='utf-8')

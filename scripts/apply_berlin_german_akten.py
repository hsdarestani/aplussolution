from pathlib import Path

# Browser language: the product is intentionally German and must not be auto-translated.
p=Path('frontend/index.html'); s=p.read_text()
s=s.replace('<html lang="de">','<html lang="de" translate="no" class="notranslate">')
s=s.replace('<meta charset="UTF-8"/>','<meta charset="UTF-8"/><meta http-equiv="Content-Language" content="de-DE"/><meta name="google" content="notranslate"/>')
p.write_text(s)

# Dedicated full-page Digital Akte routing.
p=Path('frontend/src/App.tsx'); s=p.read_text()
if "import AktePage from './AktePage';" not in s: s=s.replace("import DocumentCenterV5 from './DocumentCenterV5';", "import DocumentCenterV5 from './DocumentCenterV5';\nimport AktePage from './AktePage';")
if "| 'akte';" not in s: s=s.replace("  | 'operations';", "  | 'operations'\n  | 'akte';",1)
s=s.replace("  const [view, setView] = useState<View>('dashboard');", "  const initialView = (() => { const value = new URLSearchParams(window.location.search).get('view') as View | null; return value || 'dashboard'; })();\n  const [view, setView] = useState<View>(initialView);")
old="""    return () => window.removeEventListener('auth-lost', lost);
  }, []);
"""
new="""    const syncView = () => { const value = new URLSearchParams(window.location.search).get('view') as View | null; setView(value || 'dashboard'); };
    window.addEventListener('popstate', syncView);
    return () => { window.removeEventListener('auth-lost', lost); window.removeEventListener('popstate', syncView); };
  }, []);
"""
if old in s: s=s.replace(old,new,1)
s=s.replace("  const currentLabel = view === 'profile' ? 'Profil' : items.find(([key]) => key === view)?.[1] || 'A+ Solution';", "  const currentLabel = view === 'profile' ? 'Profil' : view === 'akte' ? 'Digitale Akte' : items.find(([key]) => key === view)?.[1] || 'A+ Solution';")
old="""  const navigateTo = (next: View) => {
    setView(next);
    setMobileMenuOpen(false);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  };
"""
new="""  const navigateTo = (next: View) => {
    setView(next);
    setMobileMenuOpen(false);
    const url = new URL(window.location.href);
    url.searchParams.set('view', next);
    if (next !== 'akte') { url.searchParams.delete('akte_kind'); url.searchParams.delete('akte_id'); }
    window.history.pushState({ view: next }, '', `${url.pathname}${url.search}${url.hash}`);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  };
"""
if old in s: s=s.replace(old,new,1)
if "<AktePage user={user} />" not in s: s=s.replace("  else if (view === 'operations') content = <Operations user={user} />;", "  else if (view === 'operations') content = <Operations user={user} />;\n  else if (view === 'akte') content = <AktePage user={user} />;")
s=s.replace("                  <small>{user.role}</small>", "                  <small>{roleLabel[user.role] || user.role}</small>")
p.write_text(s)

# Header folder opens a proper page, not a narrow drawer detail.
p=Path('frontend/src/HeaderQuickAccess.tsx'); s=p.read_text()
if "timeZone: 'Europe/Berlin'" not in s[s.find('function formatDate'):s.find('function navigateAction')]:
    s=s.replace("    hour: value.includes('T') ? '2-digit' : undefined,", "    timeZone: 'Europe/Berlin',\n    hour: value.includes('T') ? '2-digit' : undefined,",1)
old="""  const openAkte = async (choice: PersonChoice) => {
    setAkteLoading(true);
    setError('');
    try {
      const path = choice.kind === 'worker' ? `workers/${choice.id}/akte/` : `clients/${choice.id}/akte/`;
      setAkte(await api<AkteData>(path));
    } catch (reason: any) {
      setError(reason?.message || 'Akte konnte nicht geladen werden.');
    } finally {
      setAkteLoading(false);
    }
  };
"""
new="""  const openAkte = async (choice: PersonChoice) => {
    setPanel(null);
    const url = new URL(window.location.href);
    url.pathname = '/';
    url.searchParams.set('view', 'akte');
    url.searchParams.set('akte_kind', choice.kind);
    url.searchParams.set('akte_id', choice.id);
    window.history.pushState({ view: 'akte' }, '', `${url.pathname}${url.search}${url.hash}`);
    window.dispatchEvent(new PopStateEvent('popstate'));
  };
"""
if old in s: s=s.replace(old,new,1)
p.write_text(s)

# Berlin business dates, including the UTC-midnight edge case.
p=Path('frontend/src/PremiumOperations.tsx'); s=p.read_text()
s=s.replace("const isoDate = (date = new Date()) => date.toISOString().slice(0, 10);", "const isoDate = (date = new Date()) => { const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date); const get=(type:string)=>parts.find(item=>item.type===type)?.value||''; return `${get('year')}-${get('month')}-${get('day')}`; };")
p.write_text(s)

p=Path('frontend/src/Operations.tsx'); s=p.read_text()
s=s.replace("const dateTime = (input?: string) => (input ? new Date(input).toLocaleString('de-DE') : '–');", "const dateTime = (input?: string) => (input ? new Date(input).toLocaleString('de-DE', { timeZone: 'Europe/Berlin' }) : '–');")
s=s.replace("const dateOnly = (input?: string) => (input ? new Date(input).toLocaleDateString('de-DE') : '–');", "const dateOnly = (input?: string) => (input ? new Date(input).toLocaleDateString('de-DE', { timeZone: 'Europe/Berlin' }) : '–');")
if 'const berlinDateKey =' not in s:
    marker="const unpack = (value: any): any[] => value?.results || value || [];"
    helper="const berlinDateKey = (date = new Date()) => { const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date); const get=(type:string)=>parts.find(item=>item.type===type)?.value||''; return `${get('year')}-${get('month')}-${get('day')}`; };"
    if marker in s: s=s.replace(marker,marker+'\n'+helper,1)
s=s.replace("{ start: `${new Date().getFullYear()}-01-01`, end: new Date().toISOString().slice(0, 10) }", "{ start: `${berlinDateKey().slice(0,4)}-01-01`, end: berlinDateKey() }")
p.write_text(s)

p=Path('frontend/src/ScheduleV2.tsx'); s=p.read_text(); s=s.replace("new Intl.DateTimeFormat('de-DE',options).format(keyToDate(key))", "new Intl.DateTimeFormat('de-DE',{timeZone:BERLIN_TIME_ZONE,...options}).format(keyToDate(key))"); p.write_text(s)

# User-facing backend date rendering. ISO API transport values intentionally remain timezone-aware ISO.
replacements={
'backend/core/shift_views.py':[("f'{shift.starts_at:%d.%m.%Y %H:%M} – {shift.location.name}'","f'{timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M} – {shift.location.name}'"),("f'{request.user.get_full_name() or request.user.email} · {shift.starts_at:%d.%m.%Y %H:%M} · {shift.location.name}'","f'{request.user.get_full_name() or request.user.email} · {timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M} · {shift.location.name}'")],
'backend/core/admin_center_views.py':[("f'{order.client.name} · {order.starts_at:%d.%m.%Y %H:%M}'","f'{order.client.name} · {timezone.localtime(order.starts_at):%d.%m.%Y %H:%M}'"),("f'{shift.location.name} · {shift.starts_at:%d.%m.%Y %H:%M}'","f'{shift.location.name} · {timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M}'")],
'backend/core/slot_compat_views_v2.py':[("f'{obj.shift.starts_at:%d.%m.%Y %H:%M} · {obj.shift.position.name}'","f'{timezone.localtime(obj.shift.starts_at):%d.%m.%Y %H:%M} · {obj.shift.position.name}'")],
'backend/core/advanced_views.py':[("f'{shift.starts_at:%d.%m.%Y %H:%M}'","f'{timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M}'"),("entry.clock_in.astimezone().strftime('%d.%m.%Y %H:%M')","timezone.localtime(entry.clock_in).strftime('%d.%m.%Y %H:%M')"),("entry.clock_out.astimezone().strftime('%d.%m.%Y %H:%M')","timezone.localtime(entry.clock_out).strftime('%d.%m.%Y %H:%M')"),("shift.starts_at.astimezone().strftime('%d.%m.%Y %H:%M')","timezone.localtime(shift.starts_at).strftime('%d.%m.%Y %H:%M')"),("shift.ends_at.astimezone().strftime('%d.%m.%Y %H:%M')","timezone.localtime(shift.ends_at).strftime('%d.%m.%Y %H:%M')")],
'backend/core/premium_extra_views.py':[("body=f'{row.shift.starts_at:%d.%m.%Y %H:%M}'","body=f'{timezone.localtime(row.shift.starts_at):%d.%m.%Y %H:%M}'")],
'backend/core/order_automation.py':[("shift.starts_at.astimezone().strftime('%d.%m.%Y %H:%M')","timezone.localtime(shift.starts_at).strftime('%d.%m.%Y %H:%M')"),("shift.ends_at.astimezone().strftime('%d.%m.%Y %H:%M')","timezone.localtime(shift.ends_at).strftime('%d.%m.%Y %H:%M')")],
}
for path,pairs in replacements.items():
    p=Path(path); s=p.read_text()
    for old,new in pairs: s=s.replace(old,new)
    p.write_text(s)

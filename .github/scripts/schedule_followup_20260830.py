from pathlib import Path

ROOT = Path('.')


def replace_once(path: str, old: str, new: str):
    file = ROOT / path
    text = file.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected one match, found {count}: {old[:120]!r}')
    file.write_text(text.replace(old, new, 1), encoding='utf-8')


def append_once(path: str, marker: str, content: str):
    file = ROOT / path
    text = file.read_text(encoding='utf-8')
    if marker in text:
        return
    file.write_text(text.rstrip() + '\n\n' + content.strip() + '\n', encoding='utf-8')

path = 'frontend/src/WiwScheduleMobile.tsx'

replace_once(
    path,
    "  const [tab, setTab] = useState<TabKey>('all');\n  const [query, setQuery] = useState('');",
    "  const [tab, setTab] = useState<TabKey>('all');\n  const [weekDirection, setWeekDirection] = useState<'next' | 'prev' | ''>('');\n  const [query, setQuery] = useState('');",
)

replace_once(
    path,
    "  const byDay = useMemo(() => {\n    const map: Record<string, CardRow[]> = {};\n    visibleDays.forEach((day) => { map[day] = []; });\n    visibleCards.forEach((card) => { (map[dateKeyFromIso(card.shift.starts_at)] ||= []).push(card); });\n    return map;\n  }, [visibleDays, visibleCards]);",
    "  const byDay = useMemo(() => {\n    const map: Record<string, CardRow[]> = {};\n    visibleDays.forEach((day) => { map[day] = []; });\n    visibleCards.forEach((card) => { (map[dateKeyFromIso(card.shift.starts_at)] ||= []).push(card); });\n    Object.values(map).forEach((dayCards) => {\n      const firstStartByClient = new Map<string, number>();\n      dayCards.forEach((card) => {\n        const key = clientKey(card.shift);\n        const start = new Date(card.shift.starts_at).getTime();\n        firstStartByClient.set(key, Math.min(firstStartByClient.get(key) ?? Number.POSITIVE_INFINITY, start));\n      });\n      dayCards.sort((left, right) => {\n        const leftKey = clientKey(left.shift);\n        const rightKey = clientKey(right.shift);\n        const groupOrder = (firstStartByClient.get(leftKey) ?? 0) - (firstStartByClient.get(rightKey) ?? 0);\n        if (groupOrder) return groupOrder;\n        if (leftKey !== rightKey) return String(left.shift.client_name || '').localeCompare(String(right.shift.client_name || ''), 'de');\n        return new Date(left.shift.starts_at).getTime() - new Date(right.shift.starts_at).getTime();\n      });\n    });\n    return map;\n  }, [visibleDays, visibleCards]);",
)

replace_once(
    path,
    "  if (!active || !mobile || !manager) return null;\n  const host = document.querySelector('.app-main') || document.body;",
    "  function changeWeek(delta: number) {\n    setWeekDirection(delta > 0 ? 'next' : 'prev');\n    setAnchor((current) => addDays(current, delta));\n  }\n\n  if (!active || !mobile || !manager) return null;\n  const host = document.querySelector('.app-main') || document.body;",
)

replace_once(
    path,
    "          {([['all', 'Alle'], ['open', 'OpenShifts'], ['filled', 'Besetzt'], ['draft', 'Entwürfe']] as Array<[TabKey, string]>).map(([key, label]) => <button type=\"button\" role=\"tab\" aria-selected={tab === key} key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}",
    "          {([['all', 'Alle'], ['open', 'OpenShifts']] as Array<[TabKey, string]>).map(([key, label]) => <button type=\"button\" role=\"tab\" aria-selected={tab === key} key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}",
)

replace_once(
    path,
    "        <button type=\"button\" onClick={() => setAnchor(addDays(anchor, -7))}>‹</button>",
    "        <button type=\"button\" onClick={() => changeWeek(-7)}>‹</button>",
)
replace_once(
    path,
    "        <button type=\"button\" onClick={() => setAnchor(addDays(anchor, 7))}>›</button>",
    "        <button type=\"button\" onClick={() => changeWeek(7)}>›</button>",
)

replace_once(
    path,
    "      <div\n        className=\"wiw-week-scroll\"",
    "      <div\n        key={weekStart}\n        className={`wiw-week-scroll ${weekDirection ? `wiw-week-turn-${weekDirection}` : ''}`}",
)

replace_once(
    path,
    "          if (tab !== 'open' && Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.2) setAnchor(addDays(anchor, dx < 0 ? 7 : -7));",
    "          if (tab !== 'open' && Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.2) changeWeek(dx < 0 ? 7 : -7);",
)

replace_once(
    path,
    "              <div className=\"wiw-card-line secondary\"><span className={card.isOpen ? 'open' : ''}>{card.shift.position_name || 'Schicht'}</span><small>{card.shift.client_name || ''}{card.shift.location_name ? ` · ${card.shift.location_name}` : ''}</small></div>",
    "              <div className=\"wiw-card-line secondary\"><span className={card.isOpen ? 'open' : ''}>{card.shift.position_name || 'Schicht'}</span><small>{card.shift.location_name || ''}</small></div>",
)

append_once(
    'frontend/src/wiw-schedule-mobile.css',
    '/* Week-change page turn 2026-08-30 */',
    r'''/* Week-change page turn 2026-08-30 */
@media (max-width:900px){
  .wiw-week-scroll{transform-origin:50% 0;backface-visibility:hidden;perspective:1000px}
  .wiw-week-turn-next{animation:wiw-week-page-next .28s cubic-bezier(.2,.72,.25,1)}
  .wiw-week-turn-prev{animation:wiw-week-page-prev .28s cubic-bezier(.2,.72,.25,1)}
  @keyframes wiw-week-page-next{
    0%{opacity:.45;transform:translateX(18px) rotateY(-5deg) scale(.992)}
    62%{opacity:.92;transform:translateX(-2px) rotateY(.7deg) scale(1)}
    100%{opacity:1;transform:translateX(0) rotateY(0) scale(1)}
  }
  @keyframes wiw-week-page-prev{
    0%{opacity:.45;transform:translateX(-18px) rotateY(5deg) scale(.992)}
    62%{opacity:.92;transform:translateX(2px) rotateY(-.7deg) scale(1)}
    100%{opacity:1;transform:translateX(0) rotateY(0) scale(1)}
  }
  .wiw-tabs{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (prefers-reduced-motion:reduce){
  .wiw-week-turn-next,.wiw-week-turn-prev{animation:none!important}
}''',
)

text = (ROOT / path).read_text(encoding='utf-8')
assert "['filled', 'Besetzt']" not in text
assert "['draft', 'Entwürfe']" not in text
assert '<small>{card.shift.location_name || \'\'}</small>' in text
assert 'firstStartByClient' in text
assert 'wiw-week-turn-' in text
print('Dienstplan follow-up patch applied successfully')

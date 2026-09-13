import { readFileSync, writeFileSync } from 'node:fs';

const src = (name) => new URL(`../src/${name}`, import.meta.url);
const scriptAsset = (name) => new URL(name, import.meta.url);

function patchFile(name, transform) {
  const path = src(name);
  const before = readFileSync(path, 'utf8');
  const after = transform(before);
  if (after !== before) writeFileSync(path, after);
}

function replaceRequired(source, needle, replacement, label) {
  if (!source.includes(needle)) throw new Error(`SEP13 patch marker changed: ${label}`);
  return source.replace(needle, replacement);
}

patchFile('WiwScheduleMobile.tsx', (source) => {
  if (source.includes('SEP13_DIENSTPLAN_POLISH')) return source;
  let next = source;

  next = replaceRequired(
    next,
    "  { key: 'night', label: 'Nachtdienst', start: 22 * 60 + 30, end: 24 * 60 + 6 * 60 + 30 },",
    "  { key: 'night', label: 'Nachtdienst', start: 22 * 60 + 45, end: 24 * 60 + 6 * 60 + 46 },",
    'hotel night preset',
  );

  const helpers = readFileSync(scriptAsset('sep13-wiw-helpers.txt'), 'utf8').trim();
  next = replaceRequired(next, '\nfunction WheelColumn(', `\n${helpers}\n\nfunction WheelColumn(`, 'Dienstplan helpers');

  const oldSort = `  Object.values(map).forEach((dayCards) => {
    dayCards.sort((left, right) => {
      const groupOrder = clientRank(left.shift.client_name) - clientRank(right.shift.client_name);
      if (groupOrder) return groupOrder;
      const nameOrder = String(left.shift.client_name || '').localeCompare(String(right.shift.client_name || ''), 'de');
      if (nameOrder) return nameOrder;
      return new Date(left.shift.starts_at).getTime() - new Date(right.shift.starts_at).getTime();
    });
  });`;
  next = replaceRequired(next, oldSort, `  Object.values(map).forEach((dayCards) => dayCards.sort(sortScheduleCards));`, 'daily card ordering');

  const swipeStart = `\n      <div\n        key={weekStart}\n        className={\`wiw-week-scroll \${weekDirection ? \`wiw-week-turn-\${weekDirection}\` : ''}\`}`;
  const totalMarker = `\n\n      {tab !== 'open' ? <div className="wiw-week-total">`;
  const startIndex = next.indexOf(swipeStart);
  const endIndex = next.indexOf(totalMarker, startIndex);
  if (startIndex < 0 || endIndex < 0) throw new Error('SEP13 patch marker changed: week swipe block');
  const weekTemplate = readFileSync(scriptAsset('sep13-wiw-week.txt'), 'utf8').trim();
  next = `${next.slice(0, startIndex)}\n      ${weekTemplate}${next.slice(endIndex)}`;

  return `// SEP13_DIENSTPLAN_POLISH\n${next}`;
});

patchFile('AdminScheduleTools.tsx', (source) => {
  if (source.includes('SEP13_AI_POLISH')) return source;
  let next = source;

  next = replaceRequired(
    next,
    `const unpack = (value: any): any[] => value?.results || value || [];`,
    `const unpack = (value: any): any[] => value?.results || value || [];
const formatGermanDate = (value: string) => {
  const match = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(String(value || ''));
  return match ? \`${'${match[3]}.${match[2]}.${match[1]}'}\` : value;
};`,
    'AI German date formatter',
  );

  next = replaceRequired(
    next,
    `  const bypassFab = useRef(false);`,
    `  const bypassFab = useRef(false);
  const aiSheetRef = useRef<HTMLElement | null>(null);
  const aiTextareaRef = useRef<HTMLTextAreaElement | null>(null);`,
    'AI keyboard refs',
  );

  next = replaceRequired(
    next,
    `  async function parseOrder() {`,
    `  useEffect(() => {
    if (!aiOpen) return;
    const viewport = window.visualViewport;
    const sync = () => {
      const height = Math.round(viewport?.height || window.innerHeight);
      aiSheetRef.current?.style.setProperty('--admin-ai-vh', \`${'${height}px'}\`);
      if (document.activeElement === aiTextareaRef.current) {
        window.setTimeout(() => aiTextareaRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 30);
      }
    };
    sync();
    viewport?.addEventListener('resize', sync);
    viewport?.addEventListener('scroll', sync);
    return () => {
      viewport?.removeEventListener('resize', sync);
      viewport?.removeEventListener('scroll', sync);
    };
  }, [aiOpen]);

  async function parseOrder() {`,
    'AI visualViewport guard',
  );

  next = next.replace(
    `setMessage(\`${'${result.shifts?.length || 0}'} Schicht(en) erkannt. Bitte kurz prüfen.\`);`,
    `setMessage(\`${'${(result.shifts || []).reduce((sum: number, item: any) => sum + Number(item.count || 1), 0)}'} Schicht(en) erkannt. Bitte kurz prüfen.\`);`,
  );
  next = replaceRequired(next, `<section className="admin-schedule-sheet ai" role="dialog"`, `<section ref={aiSheetRef} className="admin-schedule-sheet ai" role="dialog"`, 'AI sheet ref');
  next = replaceRequired(
    next,
    `<label>Auftragstext<textarea autoFocus value={orderText}`,
    `<label>Auftragstext<textarea ref={aiTextareaRef} autoFocus onFocus={() => window.setTimeout(() => aiTextareaRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 80)} value={orderText}`,
    'AI textarea keyboard guard',
  );
  next = replaceRequired(
    next,
    `{parsed ? <div className="admin-ai-preview"><b>{parsed.shifts?.length || 0} Schicht(en) erkannt</b>{parsed.shifts?.map((item: any, index: number) => <span key={index}>{item.date} · {item.start_time}–{item.end_time} · {item.count}× {item.role} · {item.site_text}</span>)}</div> : null}`,
    `{parsed ? <div className="admin-ai-preview"><b>{(parsed.shifts || []).reduce((sum: number, item: any) => sum + Number(item.count || 1), 0)} Schicht(en) erkannt</b>{parsed.shifts?.map((item: any, index: number) => <span key={index}>{formatGermanDate(item.date)} · {item.start_time}–{item.end_time} · {item.count}× {item.role} · {item.site_text}{item.location_text ? \` · \${item.location_text}\` : ''}{item.notes ? \` · Notiz: \${item.notes}\` : ''}</span>)}</div> : null}`,
    'AI preview',
  );

  return `// SEP13_AI_POLISH\n${next}`;
});

patchFile('Phase8MobileAttendance.tsx', (source) => {
  if (source.includes('SEP13_MONTH_RANGE_POLISH')) return source;
  let next = source;
  next = replaceRequired(
    next,
    `function label(start: Date, end: Date) { return \`1. \${fmtMonth(start)} – 1. \${fmtMonth(end)} \${end.getUTCFullYear()}\`; }
function shortLabel(start: Date, end: Date) { return \`\${start.getUTCDate()}. \${fmtMonthShort(start)} – \${end.getUTCDate()}. \${fmtMonthShort(end)} \${end.getUTCFullYear()}\`; }`,
    `function periodLastDay(end: Date) { return new Date(end.getTime() - 24 * 60 * 60 * 1000); }
function label(start: Date, end: Date) { const last = periodLastDay(end); return \`1. \${fmtMonth(start)} – \${last.getUTCDate()}. \${fmtMonth(last)} \${last.getUTCFullYear()}\`; }
function shortLabel(start: Date, end: Date) { const last = periodLastDay(end); return \`\${start.getUTCDate()}. \${fmtMonthShort(start)} – \${last.getUTCDate()}. \${fmtMonthShort(last)} \${last.getUTCFullYear()}\`; }`,
    'employee month range',
  );
  return `// SEP13_MONTH_RANGE_POLISH\n${next}`;
});

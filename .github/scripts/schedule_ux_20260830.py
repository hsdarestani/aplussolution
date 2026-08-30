from pathlib import Path
import re

ROOT = Path('.')


def replace_once(path: str, old: str, new: str):
    file = ROOT / path
    text = file.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected exactly one match, found {count}: {old[:90]!r}')
    file.write_text(text.replace(old, new, 1), encoding='utf-8')


def append_once(path: str, marker: str, content: str):
    file = ROOT / path
    text = file.read_text(encoding='utf-8')
    if marker in text:
        return
    file.write_text(text.rstrip() + '\n\n' + content.strip() + '\n', encoding='utf-8')


palette_path = ROOT / 'frontend/src/scheduleClientPalette.ts'
palette_path.write_text(r'''export type SchedulePalette = {
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

const defaultPalette: SchedulePalette = {
  accent: '#0b4d6b',
  openBackground: 'linear-gradient(90deg,#e7f2f7 0%,#f4f9fb 48%,#ffffff 100%)',
  filledBackground: 'linear-gradient(90deg,#0b4d6b 0%,#1c6684 42%,#e8f2f6 100%)',
  openText: '#20313a',
  filledText: '#ffffff',
  openMuted: '#667985',
  filledMuted: '#e8f3f8',
  legendBackground: '#eaf4f8',
  legendText: '#17465a',
};

function customHuePalette(hue: number): SchedulePalette {
  return {
    accent: `hsl(${hue} 68% 42%)`,
    openBackground: `linear-gradient(90deg,hsl(${hue} 72% 91%) 0%,hsl(${hue} 60% 97%) 52%,#fff 100%)`,
    filledBackground: `linear-gradient(90deg,hsl(${hue} 63% 37%) 0%,hsl(${hue} 58% 48%) 48%,hsl(${hue} 55% 91%) 100%)`,
    openText: '#263238',
    filledText: '#ffffff',
    openMuted: '#667085',
    filledMuted: '#f4f7fb',
    legendBackground: `hsl(${hue} 72% 94%)`,
    legendText: `hsl(${hue} 55% 29%)`,
  };
}

export function schedulePalette(clientName?: string, positionName?: string, customHue?: number | null): SchedulePalette {
  if (customHue != null && Number.isFinite(Number(customHue))) return customHuePalette(Number(customHue));
  const client = normalizeScheduleLabel(clientName);
  const position = normalizeScheduleLabel(positionName);

  if (client.includes('martha')) return {
    accent: '#d97706',
    openBackground: 'linear-gradient(90deg,#ffedd5 0%,#fff7ed 55%,#ffffff 100%)',
    filledBackground: 'linear-gradient(90deg,#c86404 0%,#e98216 48%,#ffe5bd 100%)',
    openText: '#5a3412', filledText: '#ffffff', openMuted: '#8a6747', filledMuted: '#fff3e2', legendBackground: '#fff0db', legendText: '#8a4708',
  };
  if (client.includes('messefrankfurt') || client === 'messe' || client.includes('ommia') || client.includes('omnia') || client.includes('hofgut')) return {
    accent: '#b8bec7',
    openBackground: 'linear-gradient(90deg,#ffffff 0%,#ffffff 72%,#f8fafc 100%)',
    filledBackground: 'linear-gradient(90deg,#d5dae1 0%,#f0f2f5 35%,#ffffff 100%)',
    openText: '#374151', filledText: '#202733', openMuted: '#7b8490', filledMuted: '#596270', legendBackground: '#ffffff', legendText: '#4b5563',
  };
  if (client.includes('stadthausammarkt') || client.includes('stadhaus')) return {
    accent: '#815b3a',
    openBackground: 'linear-gradient(90deg,#efe6dd 0%,#f8f3ee 58%,#ffffff 100%)',
    filledBackground: 'linear-gradient(90deg,#725035 0%,#986c49 48%,#e8d7c8 100%)',
    openText: '#493425', filledText: '#ffffff', openMuted: '#7c6859', filledMuted: '#f7eee7', legendBackground: '#eee4db', legendText: '#60442f',
  };
  if (client.includes('citybeach')) return {
    accent: '#168ca5',
    openBackground: 'linear-gradient(90deg,#dff4f8 0%,#eefafd 58%,#ffffff 100%)',
    filledBackground: 'linear-gradient(90deg,#0f778d 0%,#159ab4 48%,#cceff5 100%)',
    openText: '#164b57', filledText: '#ffffff', openMuted: '#56808a', filledMuted: '#ecfbfe', legendBackground: '#ddf4f8', legendText: '#126579',
  };
  if (client.includes('hirschgarten') || client.includes('restauranthirschgarten')) return {
    accent: '#3f7d44',
    openBackground: 'linear-gradient(90deg,#e3f0e3 0%,#f2f8f2 58%,#ffffff 100%)',
    filledBackground: 'linear-gradient(90deg,#356b3a 0%,#4b8a50 48%,#d7ead8 100%)',
    openText: '#27472b', filledText: '#ffffff', openMuted: '#617963', filledMuted: '#eef8ef', legendBackground: '#e3f0e3', legendText: '#315f35',
  };
  if (isHotelClientName(clientName)) {
    if (position.includes('frontoffice')) return {
      accent: '#647d92',
      openBackground: 'linear-gradient(90deg,#eceff1 0%,#eceff1 52%,#dceaf5 100%)',
      filledBackground: 'linear-gradient(90deg,#737980 0%,#737980 52%,#4d789c 100%)',
      openText: '#38434c', filledText: '#ffffff', openMuted: '#6b747d', filledMuted: '#eef6fc', legendBackground: '#edf1f4', legendText: '#4d6070',
    };
    if (position.includes('housekeeping') || position.includes('houskeeping')) return {
      accent: '#766889',
      openBackground: 'linear-gradient(90deg,#eceff1 0%,#eceff1 52%,#e9e1f0 100%)',
      filledBackground: 'linear-gradient(90deg,#737980 0%,#737980 52%,#725d86 100%)',
      openText: '#3e4147', filledText: '#ffffff', openMuted: '#72747b', filledMuted: '#f6effa', legendBackground: '#efedf2', legendText: '#60566d',
    };
    return {
      accent: '#72777d',
      openBackground: 'linear-gradient(90deg,#eceff1 0%,#f5f6f7 58%,#ffffff 100%)',
      filledBackground: 'linear-gradient(90deg,#747980 0%,#92979d 52%,#dfe2e5 100%)',
      openText: '#3f4449', filledText: '#ffffff', openMuted: '#747a80', filledMuted: '#f7f8f9', legendBackground: '#eceff1', legendText: '#565d63',
    };
  }
  if (client.includes('hofelcatering') || client.includes('hofel') || client.includes('hoefel')) return {
    accent: '#111827',
    openBackground: 'linear-gradient(90deg,#e5e7eb 0%,#f5f6f8 58%,#ffffff 100%)',
    filledBackground: 'linear-gradient(90deg,#0b0f17 0%,#111827 58%,#333b48 100%)',
    openText: '#1f2937', filledText: '#ffffff', openMuted: '#6b7280', filledMuted: '#e5e7eb', legendBackground: '#111827', legendText: '#ffffff',
  };
  return defaultPalette;
}
''', encoding='utf-8')

# ---- WiwScheduleMobile logic ----
path = 'frontend/src/WiwScheduleMobile.tsx'
replace_once(path, "import { api } from './api';\nimport './wiw-schedule-mobile.css';", "import { api } from './api';\nimport { isHotelClientName, isHotelPositionName, schedulePalette } from './scheduleClientPalette';\nimport './wiw-schedule-mobile.css';")
replace_once(path, "  const [toast, setToast] = useState('');\n  const [formOpen, setFormOpen] = useState(false);\n  const [editing, setEditing] = useState<EditingCard>();", "  const [toast, setToast] = useState('');\n  const [formOpen, setFormOpen] = useState(false);\n  const [editing, setEditing] = useState<EditingCard>();\n  const [copying, setCopying] = useState(false);")
replace_once(path, "  const swipe = useRef<{ x: number; y: number } | undefined>(undefined);\n\n  useEffect(() => {", "  const swipe = useRef<{ x: number; y: number } | undefined>(undefined);\n\n  useEffect(() => {\n    if (!toast) return;\n    const timer = window.setTimeout(() => setToast(''), 1000);\n    return () => window.clearTimeout(timer);\n  }, [toast]);\n\n  useEffect(() => {")

old_wheel = r'''function WheelColumn({ items, value, onChange }: { items: Array<{ value: number; label: string }>; value: number; onChange: (value: number) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    const index = Math.max(0, items.findIndex((item) => item.value === value));
    if (ref.current) ref.current.scrollTop = index * WHEEL_ROW;
  }, [items, value]);
  const settle = () => {
    if (!ref.current) return;
    const index = Math.max(0, Math.min(items.length - 1, Math.round(ref.current.scrollTop / WHEEL_ROW)));
    ref.current.scrollTo({ top: index * WHEEL_ROW, behavior: 'smooth' });
    onChange(items[index].value);
  };
  return (
    <div
      ref={ref}
      className="wiw-wheel-column"
      onScroll={() => {
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(settle, 80);
      }}
      onPointerUp={settle}
    >
      {items.map((item) => (
        <button type="button" key={item.value} className={item.value === value ? 'active' : ''} onClick={() => onChange(item.value)}>{item.label}</button>
      ))}
    </div>
  );
}'''
new_wheel = r'''function WheelColumn({ items, value, onChange }: { items: Array<{ value: number; label: string }>; value: number; onChange: (value: number) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const userScrolling = useRef(false);
  const programmatic = useRef(false);
  const latestValue = useRef(value);

  useEffect(() => { latestValue.current = value; }, [value]);
  useEffect(() => {
    if (!ref.current || userScrolling.current) return;
    const index = Math.max(0, items.findIndex((item) => item.value === value));
    const target = index * WHEEL_ROW;
    if (Math.abs(ref.current.scrollTop - target) > 1) ref.current.scrollTop = target;
  }, [items, value]);

  const settle = () => {
    if (!ref.current || !items.length) return;
    const index = Math.max(0, Math.min(items.length - 1, Math.round(ref.current.scrollTop / WHEEL_ROW)));
    const target = index * WHEEL_ROW;
    const next = items[index].value;
    programmatic.current = true;
    ref.current.scrollTo({ top: target, behavior: 'smooth' });
    if (next !== latestValue.current) {
      latestValue.current = next;
      onChange(next);
    }
    window.setTimeout(() => {
      programmatic.current = false;
      userScrolling.current = false;
    }, 190);
  };

  return (
    <div
      ref={ref}
      className="wiw-wheel-column"
      onScroll={() => {
        if (programmatic.current) return;
        userScrolling.current = true;
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(settle, 150);
      }}
    >
      {items.map((item) => (
        <button type="button" key={item.value} className={item.value === value ? 'active' : ''} onClick={() => {
          latestValue.current = item.value;
          onChange(item.value);
          ref.current?.scrollTo({ top: items.findIndex((candidate) => candidate.value === item.value) * WHEEL_ROW, behavior: 'smooth' });
        }}>{item.label}</button>
      ))}
    </div>
  );
}'''
replace_once(path, old_wheel, new_wheel)

old_colors = r'''  const clientHueMap = useMemo(() => {
    const keys = Array.from(new Set(rows.map(clientKey))).sort();
    return new Map(keys.map((key, index) => [key, (18 + index * 137.508) % 360]));
  }, [rows]);
  const effectiveHue = (shift: any) => shift?.color_hue == null ? (clientHueMap.get(clientKey(shift)) ?? 215) : Number(shift.color_hue);
  const formAutoHue = clientHueMap.get(form.client || 'ohne-kunde') ?? 215;'''
new_colors = r'''  const shiftCardStyle = (shift: any) => {
    const palette = schedulePalette(shift?.client_name, shift?.position_name, shift?.color_hue);
    return {
      '--wiw-card-accent': palette.accent,
      '--wiw-card-open-bg': palette.openBackground,
      '--wiw-card-filled-bg': palette.filledBackground,
      '--wiw-card-open-text': palette.openText,
      '--wiw-card-filled-text': palette.filledText,
      '--wiw-card-open-muted': palette.openMuted,
      '--wiw-card-filled-muted': palette.filledMuted,
    } as React.CSSProperties;
  };
  const selectedClientName = clients.find((item: any) => String(item.id) === form.client)?.name || '';
  const selectedPositionName = positions.find((item: any) => String(item.id) === form.position)?.name || '';
  const formPalette = schedulePalette(selectedClientName, selectedPositionName, form.color_hue);
  const formAutoHue = 215;'''
replace_once(path, old_colors, new_colors)

old_position_choices = r'''  const positionChoices = useMemo<Choice[]>(() => POSITION_ORDER.flatMap((definition) => {
    const match = positions.find((item: any) => definition.aliases.includes(normalize(item.name)));
    return match ? [{ value: String(match.id), label: definition.label }] : [];
  }), [positions]);'''
new_position_choices = r'''  const positionChoices = useMemo<Choice[]>(() => {
    const hotelOnly = isHotelClientName(clients.find((item: any) => String(item.id) === form.client)?.name);
    return POSITION_ORDER.flatMap((definition) => {
      const match = positions.find((item: any) => definition.aliases.includes(normalize(item.name)));
      if (!match) return [];
      if (hotelOnly && !isHotelPositionName(match.name)) return [];
      return [{ value: String(match.id), label: definition.label }];
    });
  }, [positions, clients, form.client]);'''
replace_once(path, old_position_choices, new_position_choices)

replace_once(path, "  function openCreate(date = anchor) {\n    setEditing(undefined);", "  function openCreate(date = anchor) {\n    setEditing(undefined);\n    setCopying(false);")
replace_once(path, "  function openEdit(card: CardRow) {\n    const startDate", "  function openEdit(card: CardRow) {\n    setCopying(false);\n    const startDate")

old_copy = r'''  async function copyEditingAsOpenShift() {
    if (!editing || busy || !form.client || !form.location || !form.position || form.startMinute == null || form.endAbsolute == null) return;
    setBusy(true);
    let createdId = '';
    try {
      const payload: any = {
        client: form.client,
        location: form.location,
        position: form.position,
        starts_at: localDateTime(form.date, form.startMinute),
        ends_at: localDateTime(form.date, form.endAbsolute),
        break_minutes: automaticBreak(form.startMinute, form.endAbsolute),
        notes: form.notes || '',
        confirmation_required: form.confirmation_required,
        schedule_groups: form.schedule_groups,
        color_hue: form.color_hue,
        required_count: 1,
        status: 'published',
      };
      const created: any = await api('shifts/', { method: 'POST', body: JSON.stringify(payload) });
      createdId = String(created.id || '');
      await api(`shifts/${created.id}/assign/`, {
        method: 'POST',
        body: JSON.stringify({ workers: [], publish_remaining: true }),
      });
      createdId = '';
      setFormOpen(false);
      setEditing(undefined);
      setTab('open');
      setToast('Schicht wurde ohne Mitarbeiter als OpenShift kopiert.');
      window.dispatchEvent(new Event('aplus:dashboard-invalidated'));
      await load();
    } catch (error: any) {
      if (createdId) {
        try { await api(`shifts/${createdId}/`, { method: 'DELETE' }); } catch {}
      }
      setToast(error.message || 'Schicht konnte nicht kopiert werden.');
    } finally {
      setBusy(false);
    }
  }'''
new_copy = r'''  function prepareCopyAsOpenShift() {
    if (!editing || busy) return;
    setEditing(undefined);
    setCopying(true);
    setForm((current) => ({
      ...current,
      required_count: 1,
      publish_now: true,
      workers: [],
      apply_all: false,
    }));
    setToast('Kopie bereit. Änderungen vornehmen und dann sichern.');
  }'''
replace_once(path, old_copy, new_copy)

replace_once(path, "  async function save() {\n    if (!form.client", "  async function save() {\n    const savingCopy = copying;\n    if (!form.client")
replace_once(path, "      setFormOpen(false);\n      window.dispatchEvent(new Event('aplus:dashboard-invalidated'));", "      if (savingCopy) setTab('all');\n      setCopying(false);\n      setFormOpen(false);\n      window.dispatchEvent(new Event('aplus:dashboard-invalidated'));")

old_card = r'''            {dayCards.map((card) => <button type="button" className="wiw-shift-card" style={{ '--wiw-shift-hue': String(effectiveHue(card.shift)) } as React.CSSProperties} key={card.key} onClick={() => card.shift.read_only ? setToast('WIW OpenShift · schreibgeschützt') : openEdit(card)}>
              <div className="wiw-card-line primary"><b>{card.worker?.name || (card.shift.status === 'draft' ? 'Entwurf' : 'OpenShift')}</b><span>{formatTimeIso(card.shift.starts_at)}–{formatTimeIso(card.shift.ends_at)}</span></div>'''
new_card = r'''            {dayCards.map((card) => <button type="button" className={`wiw-shift-card ${card.shift.status === 'draft' ? 'is-draft' : card.isOpen ? 'is-open' : 'is-filled'}`} style={shiftCardStyle(card.shift)} key={card.key} onClick={() => card.shift.read_only ? setToast('WIW OpenShift · schreibgeschützt') : openEdit(card)}>
              <div className="wiw-card-line primary"><b>{card.worker?.name || (card.shift.status === 'draft' ? 'Entwurf' : 'OpenShift')}{card.isOpen && card.shift.status !== 'draft' ? <span className="wiw-open-alert">!</span> : null}</b><span>{formatTimeIso(card.shift.starts_at)}–{formatTimeIso(card.shift.ends_at)}</span></div>'''
replace_once(path, old_card, new_card)

replace_once(path, "<header className=\"wiw-form-topbar\"><button type=\"button\" onClick={() => setFormOpen(false)}>Abbrechen</button><strong>{editing ? 'Bearbeite Schicht' : 'Erstelle Schicht'}</strong>", "<header className=\"wiw-form-topbar\"><button type=\"button\" onClick={() => setFormOpen(false)}>Abbrechen</button><strong>{copying ? 'Kopie bearbeiten' : editing ? 'Bearbeite Schicht' : 'Erstelle Schicht'}</strong>")

old_client_select = "{sheet === 'client' ? <ChoiceSheet title=\"Kunde\" choices={clientChoices} selected={form.client} onClose={() => setSheet('')} onSelect={(choice) => { setForm((current) => ({ ...current, client: choice.value, location: '' })); setSheet(''); }} /> : null}"
new_client_select = "{sheet === 'client' ? <ChoiceSheet title=\"Kunde\" choices={clientChoices} selected={form.client} onClose={() => setSheet('')} onSelect={(choice) => { const nextName = clients.find((item: any) => String(item.id) === choice.value)?.name; setForm((current) => { const currentPosition = positions.find((item: any) => String(item.id) === current.position); return { ...current, client: choice.value, location: '', position: isHotelClientName(nextName) && !isHotelPositionName(currentPosition?.name) ? '' : current.position }; }); setSheet(''); }} /> : null}"
replace_once(path, old_client_select, new_client_select)

replace_once(path, "style={{ '--wiw-color-hue': String(form.color_hue ?? formAutoHue) } as React.CSSProperties}", "style={form.color_hue == null ? ({ background: formPalette.accent } as React.CSSProperties) : ({ '--wiw-color-hue': String(form.color_hue ?? formAutoHue) } as React.CSSProperties)}")
replace_once(path, "<Row icon={copyOutline} label=\"Schicht als OpenShift kopieren\" value=\"Ohne Mitarbeiter\" onClick={() => void copyEditingAsOpenShift()} />", "<Row icon={copyOutline} label=\"Schicht als OpenShift kopieren\" value=\"Danach bearbeiten & sichern\" onClick={prepareCopyAsOpenShift} />")

# ---- Wiw mobile CSS ----
append_once('frontend/src/wiw-schedule-mobile.css', '/* A+ schedule UX polish 2026-08-30 */', r'''/* A+ schedule UX polish 2026-08-30 */
@media (max-width:900px){
  .wiw-day-section>header{height:42px;padding:0 13px;gap:8px}
  .wiw-day-section>header strong{font-size:15px;font-weight:800;letter-spacing:.01em;color:#444}
  .wiw-day-section>header span{font-size:14px;font-weight:800;color:#555}
  .wiw-week-strip small{font-size:10px;font-weight:750}
  .wiw-week-strip b{font-size:13px;font-weight:750}

  .wiw-shift-card{border-left-color:var(--wiw-card-accent,#0b4d6b);transition:background .16s ease,border-color .16s ease,box-shadow .16s ease}
  .wiw-shift-card.is-open{background:var(--wiw-card-open-bg,#f6fafc);color:var(--wiw-card-open-text,#27343b);border-left-color:color-mix(in srgb,var(--wiw-card-accent,#0b4d6b) 62%,#fff);box-shadow:inset 0 1px 0 rgba(255,255,255,.65)}
  .wiw-shift-card.is-filled{background:var(--wiw-card-filled-bg,#dceaf0);color:var(--wiw-card-filled-text,#fff);border-left-color:var(--wiw-card-accent,#0b4d6b);box-shadow:0 1px 3px rgba(22,34,45,.16)}
  .wiw-shift-card.is-draft{background:#f7f7f7;border-left-color:#aeb4ba}
  .wiw-shift-card.is-open .wiw-card-line.primary b,.wiw-shift-card.is-open .wiw-card-line.primary span{color:var(--wiw-card-open-text,#27343b)}
  .wiw-shift-card.is-open .wiw-card-line.secondary>span,.wiw-shift-card.is-open .wiw-card-line.secondary small{color:var(--wiw-card-open-muted,#6b7680)}
  .wiw-shift-card.is-filled .wiw-card-line.primary b,.wiw-shift-card.is-filled .wiw-card-line.primary span{color:var(--wiw-card-filled-text,#fff);font-weight:750}
  .wiw-shift-card.is-filled .wiw-card-line.secondary>span,.wiw-shift-card.is-filled .wiw-card-line.secondary small{color:var(--wiw-card-filled-muted,#eef4f7)}
  .wiw-open-alert{display:inline-grid;place-items:center;margin-left:6px;width:18px;height:18px;border-radius:50%;background:#f59e0b;color:#fff;font-size:12px;font-weight:900;vertical-align:1px;box-shadow:0 1px 3px rgba(0,0,0,.12)}

  .wiw-wheel-column{scroll-snap-type:y proximity;overscroll-behavior-y:contain;touch-action:pan-y;-webkit-overflow-scrolling:touch}
  .wiw-wheel-column button{scroll-snap-stop:normal}
  .wiw-toast{animation:wiw-toast-in .12s ease-out}
  @keyframes wiw-toast-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
}''')

# ---- Shift form enhancer transient message ----
path = 'frontend/src/WiwShiftFormUxEnhancer.tsx'
replace_once(path, "  const [message, setMessage] = useState('');\n\n  useEffect(() => {", "  const [message, setMessage] = useState('');\n\n  useEffect(() => {\n    if (!message) return;\n    const timer = window.setTimeout(() => setMessage(''), 1000);\n    return () => window.clearTimeout(timer);\n  }, [message]);\n\n  useEffect(() => {")

# ---- ScheduleV2 shared palette + hotel position restriction + open marker ----
path = 'frontend/src/ScheduleV2.tsx'
replace_once(path, "import { enrichLocationPayload } from './locationPicker';\nimport './schedule-v2.css';", "import { enrichLocationPayload } from './locationPicker';\nimport { isHotelClientName, isHotelPositionName, schedulePalette } from './scheduleClientPalette';\nimport './schedule-v2.css';")
replace_once(path, "  return {open,label:x.status==='draft'?'Entwurf':open?'Offen':'Voll',color:x.status==='draft'?'medium':open?'primary':'success'};", "  return {open,label:x.status==='draft'?'Entwurf':open?'Offen !':'Voll',color:x.status==='draft'?'medium':open?'primary':'success'};")
old_style = r'''  const clientHueMap=useMemo(()=>{
    const keys=Array.from(new Set(rows.map(clientKey))).sort();
    return new Map(keys.map((key,index)=>[key,(18+index*137.508)%360]));
  },[rows]);
  const clientStyle=(item:any)=>({'--sv2-client-hue':String(item?.color_hue ?? clientHueMap.get(clientKey(item)) ?? 215)} as React.CSSProperties);'''
new_style = r'''  const clientStyle=(item:any)=>{
    const palette=schedulePalette(item?.client_name,item?.position_name,item?.color_hue);
    const open=item?.status==='published'&&Number(item?.open_count||0)>0;
    return {
      '--sv2-client-accent':palette.accent,
      '--sv2-client-bg':open?palette.openBackground:palette.filledBackground,
      '--sv2-client-text':open?palette.openText:palette.filledText,
      '--sv2-client-muted':open?palette.openMuted:palette.filledMuted,
      '--sv2-client-chip':palette.legendBackground,
      '--sv2-client-chip-text':palette.legendText,
    } as React.CSSProperties;
  };'''
replace_once(path, old_style, new_style)

old_client = "<IonSelect fill=\"outline\" label=\"Kunde *\" labelPlacement=\"floating\" value={form.client} onIonChange={e=>{const id=val(e);const selected=clients.find(x=>x.id===id);const groups=scheduleGroupsForClient(selected?.name);setForm({...form,client:id,location:undefined,schedule_groups:groups.length?groups:form.schedule_groups||[]});}}>{clients.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>"
new_client = "<IonSelect fill=\"outline\" label=\"Kunde *\" labelPlacement=\"floating\" value={form.client} onIonChange={e=>{const id=val(e);const selected=clients.find(x=>x.id===id);const groups=scheduleGroupsForClient(selected?.name);const currentPosition=positions.find(x=>x.id===form.position);setForm({...form,client:id,location:undefined,position:isHotelClientName(selected?.name)&&!isHotelPositionName(currentPosition?.name)?undefined:form.position,schedule_groups:groups.length?groups:form.schedule_groups||[]});}}>{clients.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>"
replace_once(path, old_client, new_client)
old_position = "<IonSelect fill=\"outline\" label=\"Position *\" labelPlacement=\"floating\" value={form.position} onIonChange={e=>{const id=val(e);const position=positions.find(x=>x.id===id);const client=clients.find(x=>x.id===form.client);const clientGroups=scheduleGroupsForClient(client?.name);setForm({...form,position:id,schedule_groups:clientGroups.length?clientGroups:scheduleGroupsForPosition(position?.name)});}}>{positions.map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>"
new_position = "<IonSelect fill=\"outline\" label=\"Position *\" labelPlacement=\"floating\" value={form.position} onIonChange={e=>{const id=val(e);const position=positions.find(x=>x.id===id);const client=clients.find(x=>x.id===form.client);const clientGroups=scheduleGroupsForClient(client?.name);const groups=isHotelClientName(client?.name)?scheduleGroupsForPosition(position?.name):(clientGroups.length?clientGroups:scheduleGroupsForPosition(position?.name));setForm({...form,position:id,schedule_groups:groups});}}>{positions.filter(x=>!isHotelClientName(clients.find(client=>client.id===form.client)?.name)||isHotelPositionName(x.name)).map(x=><IonSelectOption key={x.id} value={x.id}>{x.name}</IonSelectOption>)}</IonSelect>"
replace_once(path, old_position, new_position)

# transient ScheduleV2 toast is handled by global IonToast duration replacement below.

# ---- ScheduleV2 CSS variable palette + stronger date typography ----
append_once('frontend/src/schedule-v2.css', '/* Fixed A+ customer palette 2026-08-30 */', r'''/* Fixed A+ customer palette 2026-08-30 */
.sv2-card,.sv2-event{border-left-color:var(--sv2-client-accent,#0b4d6b)!important;background:var(--sv2-client-bg,#fff)!important;color:var(--sv2-client-text,#101828)!important}
.sv2-event:hover{background:var(--sv2-client-bg,#fff)!important;filter:brightness(.985)}
.sv2-card .sv2-date{background:var(--sv2-client-chip,#f2f5fb)!important;color:var(--sv2-client-chip-text,#344054)!important}
.sv2-card .sv2-meter span{background:var(--sv2-client-accent,#0b4d6b)!important}
.sv2-event small,.sv2-event .sv2-field-copy small,.sv2-event .sv2-field-copy>span,.sv2-card .sv2-body em{color:var(--sv2-client-muted,#667085)!important}
.sv2-client-label{color:var(--sv2-client-chip-text,#344054)!important}.sv2-client-label i,.sv2-client-legend i{background:var(--sv2-client-accent,#0b4d6b)!important}
.sv2-client-legend>span{background:var(--sv2-client-chip,#f5f7fa)!important;color:var(--sv2-client-chip-text,#344054)!important;border-color:color-mix(in srgb,var(--sv2-client-accent,#9aa4b2) 35%,#fff)!important}
@media(max-width:900px){
  .sv2-week-day>header b,.sv2-week-day>header span{font-size:14px!important;font-weight:800!important}
  .sv2-single-day>header small{font-size:15px!important;font-weight:800!important}
  .sv2-single-day>header h2{font-size:22px!important;font-weight:850!important}
  .sv2-wiw-week-strip button span{font-weight:800!important}
  .sv2-wiw-week-strip button b{font-weight:850!important}
}''')

# ---- All Ionic in-app toasts: one second ----
for tsx in (ROOT / 'frontend/src').rglob('*.tsx'):
    text = tsx.read_text(encoding='utf-8')
    updated = re.sub(r'(\bduration=)\{\d+\}', r'\g<1>{1000}', text)
    if updated != text:
        tsx.write_text(updated, encoding='utf-8')

# Basic invariants so a future source drift fails loudly instead of publishing half the UX.
wiw = (ROOT / 'frontend/src/WiwScheduleMobile.tsx').read_text(encoding='utf-8')
assert "setTab('open')" not in wiw[wiw.find('function prepareCopyAsOpenShift'):wiw.find('async function save')]
assert "setTab('all')" in wiw
assert 'Kopie bearbeiten' in wiw
assert 'isHotelPositionName' in wiw
assert 'wiw-open-alert' in wiw
sv2 = (ROOT / 'frontend/src/ScheduleV2.tsx').read_text(encoding='utf-8')
assert "open?'Offen !'" in sv2
assert 'isHotelClientName' in sv2 and 'isHotelPositionName' in sv2
print('Schedule UX patch applied successfully')

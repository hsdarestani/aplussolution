from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def write(path, text):
    (ROOT / path).write_text(text, encoding='utf-8')


def replace_once(path, old, new):
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected exactly 1 match, got {count}: {old[:140]!r}')
    write(path, text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Admin WIW time wheel: live 15-minute ticks while the finger is moving.
# The previous implementation waited for a 150ms idle debounce before updating,
# which felt sticky and visually skipped intermediate rows.
# ---------------------------------------------------------------------------
old_wheel = r'''function WheelColumn({ items, value, onChange }: { items: Array<{ value: number; label: string }>; value: number; onChange: (value: number) => void }) {
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
new_wheel = r'''function WheelColumn({ items, value, onChange }: { items: Array<{ value: number; label: string }>; value: number; onChange: (value: number) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const settleTimer = useRef<number | undefined>(undefined);
  const frame = useRef<number | undefined>(undefined);
  const userScrolling = useRef(false);
  const programmatic = useRef(false);
  const latestValue = useRef(value);
  const lastTickIndex = useRef(-1);

  useEffect(() => { latestValue.current = value; }, [value]);
  useEffect(() => {
    if (!ref.current || userScrolling.current) return;
    const index = Math.max(0, items.findIndex((item) => item.value === value));
    lastTickIndex.current = index;
    const target = index * WHEEL_ROW;
    if (Math.abs(ref.current.scrollTop - target) > 1) ref.current.scrollTop = target;
  }, [items, value]);
  useEffect(() => () => {
    window.clearTimeout(settleTimer.current);
    if (frame.current) window.cancelAnimationFrame(frame.current);
  }, []);

  const indexAtScroll = () => {
    if (!ref.current || !items.length) return 0;
    return Math.max(0, Math.min(items.length - 1, Math.round(ref.current.scrollTop / WHEEL_ROW)));
  };

  const emitTick = () => {
    frame.current = undefined;
    const index = indexAtScroll();
    if (index === lastTickIndex.current) return;
    lastTickIndex.current = index;
    const next = items[index]?.value;
    if (next == null || next === latestValue.current) return;
    latestValue.current = next;
    onChange(next);
    try { navigator.vibrate?.(4); } catch { /* haptic is best-effort */ }
  };

  const settle = () => {
    if (!ref.current || !items.length) return;
    const index = indexAtScroll();
    const target = index * WHEEL_ROW;
    const next = items[index].value;
    lastTickIndex.current = index;
    if (next !== latestValue.current) {
      latestValue.current = next;
      onChange(next);
    }
    programmatic.current = true;
    ref.current.scrollTo({ top: target, behavior: 'smooth' });
    window.setTimeout(() => {
      programmatic.current = false;
      userScrolling.current = false;
    }, 115);
  };

  return (
    <div
      ref={ref}
      className="wiw-wheel-column"
      onScroll={() => {
        if (programmatic.current) return;
        userScrolling.current = true;
        if (!frame.current) frame.current = window.requestAnimationFrame(emitTick);
        window.clearTimeout(settleTimer.current);
        settleTimer.current = window.setTimeout(settle, 72);
      }}
    >
      {items.map((item) => (
        <button type="button" key={item.value} className={item.value === value ? 'active' : ''} onClick={() => {
          const index = items.findIndex((candidate) => candidate.value === item.value);
          latestValue.current = item.value;
          lastTickIndex.current = index;
          onChange(item.value);
          try { navigator.vibrate?.(4); } catch { /* best-effort */ }
          programmatic.current = true;
          ref.current?.scrollTo({ top: index * WHEEL_ROW, behavior: 'smooth' });
          window.setTimeout(() => { programmatic.current = false; userScrolling.current = false; }, 115);
        }}>{item.label}</button>
      ))}
    </div>
  );
}'''
replace_once('frontend/src/WiwScheduleMobile.tsx', old_wheel, new_wheel)

# Live swipe feedback follows the finger before the stronger page-turn entrance.
old_touch = r'''        onTouchStart={(event) => { const touch = event.touches[0]; swipe.current = { x: touch.clientX, y: touch.clientY }; }}
        onTouchEnd={(event) => {
          if (!swipe.current || !event.changedTouches.length) return;
          const touch = event.changedTouches[0];
          const dx = touch.clientX - swipe.current.x;
          const dy = touch.clientY - swipe.current.y;
          swipe.current = undefined;
          if (tab !== 'open' && Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.2) changeWeek(dx < 0 ? 7 : -7);
        }}'''
new_touch = r'''        onTouchStart={(event) => {
          const touch = event.touches[0];
          swipe.current = { x: touch.clientX, y: touch.clientY };
          event.currentTarget.classList.add('is-swipe-dragging');
        }}
        onTouchMove={(event) => {
          if (!swipe.current || !event.touches.length || tab === 'open') return;
          const touch = event.touches[0];
          const dx = touch.clientX - swipe.current.x;
          const dy = touch.clientY - swipe.current.y;
          if (Math.abs(dx) < Math.abs(dy) * 1.05) return;
          const travel = Math.max(-118, Math.min(118, dx * .56));
          const rotate = Math.max(-9, Math.min(9, dx / 18));
          event.currentTarget.style.transform = `translate3d(${travel}px,0,0) rotateY(${rotate}deg) scale(.985)`;
          event.currentTarget.style.opacity = String(Math.max(.58, 1 - Math.abs(dx) / 520));
        }}
        onTouchEnd={(event) => {
          event.currentTarget.classList.remove('is-swipe-dragging');
          event.currentTarget.style.transform = '';
          event.currentTarget.style.opacity = '';
          if (!swipe.current || !event.changedTouches.length) return;
          const touch = event.changedTouches[0];
          const dx = touch.clientX - swipe.current.x;
          const dy = touch.clientY - swipe.current.y;
          swipe.current = undefined;
          if (tab !== 'open' && Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.15) changeWeek(dx < 0 ? 7 : -7);
        }}
        onTouchCancel={(event) => {
          swipe.current = undefined;
          event.currentTarget.classList.remove('is-swipe-dragging');
          event.currentTarget.style.transform = '';
          event.currentTarget.style.opacity = '';
        }}'''
replace_once('frontend/src/WiwScheduleMobile.tsx', old_touch, new_touch)

# ---------------------------------------------------------------------------
# Employee release sheet: render the modal itself to document.body so no app
# stacking context/mobile tab bar can sit above its action buttons.
# ---------------------------------------------------------------------------
employee = read('frontend/src/WiwEmployeeScheduleMobile.tsx')
old_return_start = "  return createPortal(<>\n    {screen}\n    {releaseTarget && <div className=\"wiw-release-backdrop\" role=\"presentation\" onClick={closeReleaseChooser}>"
new_return_start = "  return <>\n    {createPortal(screen, host)}\n    {releaseTarget ? createPortal(<div className=\"wiw-release-backdrop\" role=\"presentation\" onClick={closeReleaseChooser}>"
if employee.count(old_return_start) != 1:
    raise RuntimeError('WiwEmployeeScheduleMobile: release portal start mismatch')
employee = employee.replace(old_return_start, new_return_start, 1)
old_return_end = "    </div>}\n  </>, host);\n}"
new_return_end = "    </div>, document.body) : null}\n  </>;\n}"
if employee.count(old_return_end) != 1:
    raise RuntimeError('WiwEmployeeScheduleMobile: release portal end mismatch')
employee = employee.replace(old_return_end, new_return_end, 1)
write('frontend/src/WiwEmployeeScheduleMobile.tsx', employee)

# ---------------------------------------------------------------------------
# CSS: mandatory row snapping + obvious active tick, and a much stronger week
# transition. Release overlay gets a guaranteed top-level modal layer.
# ---------------------------------------------------------------------------
css = read('frontend/src/wiw-schedule-mobile.css')
old_override = r'''  .wiw-wheel-column{scroll-snap-type:y proximity;overscroll-behavior-y:contain;touch-action:pan-y;-webkit-overflow-scrolling:touch}
  .wiw-wheel-column button{scroll-snap-stop:normal}'''
new_override = r'''  .wiw-wheel-column{scroll-snap-type:y mandatory;overscroll-behavior-y:contain;touch-action:pan-y;-webkit-overflow-scrolling:touch;scroll-behavior:auto}
  .wiw-wheel-column button{scroll-snap-stop:always;transition:transform .065s ease,color .065s ease,opacity .065s ease,font-size .065s ease,font-weight .065s ease;opacity:.46;transform:scale(.91)}
  .wiw-wheel-column button.active{opacity:1;transform:scale(1.13);font-weight:850;color:#263746}
  .wiw-wheel-highlight{background:linear-gradient(180deg,#e4e8eb,#f3f5f6);box-shadow:inset 0 1px 0 #fff,inset 0 -1px 0 #d4d9de}
  .wiw-time-wheel:before,.wiw-time-wheel:after{content:'';position:absolute;z-index:3;left:0;right:0;height:58px;pointer-events:none}
  .wiw-time-wheel:before{top:0;background:linear-gradient(#fafafa,rgba(250,250,250,0))}
  .wiw-time-wheel:after{bottom:0;background:linear-gradient(rgba(250,250,250,0),#fafafa)}'''
if css.count(old_override) != 1:
    raise RuntimeError('wiw-schedule-mobile.css: wheel override mismatch')
css = css.replace(old_override, new_override, 1)

old_week = r'''  .wiw-week-scroll{transform-origin:50% 0;backface-visibility:hidden;perspective:1000px}
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
  }'''
new_week = r'''  .wiw-week-scroll{transform-origin:50% 0;backface-visibility:hidden;perspective:1000px;will-change:transform,opacity,filter}
  .wiw-week-scroll.is-swipe-dragging{transition:none!important;filter:drop-shadow(0 10px 14px rgba(9,30,51,.12))}
  .wiw-week-turn-next{animation:wiw-week-page-next .41s cubic-bezier(.12,.82,.18,1)}
  .wiw-week-turn-prev{animation:wiw-week-page-prev .41s cubic-bezier(.12,.82,.18,1)}
  @keyframes wiw-week-page-next{
    0%{opacity:.18;transform:translate3d(24vw,0,0) rotateY(-11deg) scale(.965);filter:blur(2px)}
    55%{opacity:.94;transform:translate3d(-3.5vw,0,0) rotateY(1.8deg) scale(1.006);filter:blur(0)}
    78%{transform:translate3d(1.1vw,0,0) rotateY(-.5deg) scale(1)}
    100%{opacity:1;transform:translate3d(0,0,0) rotateY(0) scale(1);filter:blur(0)}
  }
  @keyframes wiw-week-page-prev{
    0%{opacity:.18;transform:translate3d(-24vw,0,0) rotateY(11deg) scale(.965);filter:blur(2px)}
    55%{opacity:.94;transform:translate3d(3.5vw,0,0) rotateY(-1.8deg) scale(1.006);filter:blur(0)}
    78%{transform:translate3d(-1.1vw,0,0) rotateY(.5deg) scale(1)}
    100%{opacity:1;transform:translate3d(0,0,0) rotateY(0) scale(1);filter:blur(0)}
  }'''
if css.count(old_week) != 1:
    raise RuntimeError('wiw-schedule-mobile.css: week animation mismatch')
css = css.replace(old_week, new_week, 1)
write('frontend/src/wiw-schedule-mobile.css', css)

release_css = read('frontend/src/wiw-employee-schedule-mobile.css')
old_release = """  .wiw-release-backdrop {
    position: fixed;
    z-index: 10020;
    inset: 0;"""
new_release = """  .wiw-release-backdrop {
    position: fixed;
    z-index: 30000;
    isolation: isolate;
    inset: 0;"""
if release_css.count(old_release) != 1:
    raise RuntimeError('release backdrop mismatch')
release_css = release_css.replace(old_release, new_release, 1)
old_sheet_padding = "    padding: 8px 18px calc(18px + env(safe-area-inset-bottom));"
new_sheet_padding = "    padding: 8px 18px calc(24px + env(safe-area-inset-bottom));"
if release_css.count(old_sheet_padding) != 1:
    raise RuntimeError('release sheet padding mismatch')
release_css = release_css.replace(old_sheet_padding, new_sheet_padding, 1)
write('frontend/src/wiw-employee-schedule-mobile.css', release_css)

# Source-level acceptance assertions complement the existing real Playwright
# release-flow tests, which will verify the pointer interception is truly gone.
phase8_path = 'frontend/e2e/phase8-wiw-mobile.spec.ts'
phase8 = read(phase8_path)
marker = "test('WIW motion uses live quarter-hour ticks and strong swipe feedback'"
if marker not in phase8:
    phase8 += r'''

test('WIW motion uses live quarter-hour ticks and strong swipe feedback', async()=>{
  const schedule=read('src/WiwScheduleMobile.tsx');
  const css=read('src/wiw-schedule-mobile.css');
  const employee=read('src/WiwEmployeeScheduleMobile.tsx');
  expect(schedule).toContain('window.requestAnimationFrame(emitTick)');
  expect(schedule).toContain('navigator.vibrate?.(4)');
  expect(schedule).toContain("classList.add('is-swipe-dragging')");
  expect(css).toContain('scroll-snap-type:y mandatory');
  expect(css).toContain('scroll-snap-stop:always');
  expect(css).toContain('translate3d(24vw,0,0)');
  expect(employee).toContain('</div>, document.body) : null}');
});
'''
    write(phase8_path, phase8)

print('final_wiw_motion_patch: OK')

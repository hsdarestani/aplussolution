import { readFileSync, writeFileSync } from 'node:fs';

const path = new URL('../src/WiwScheduleMobile.tsx', import.meta.url);
const source = readFileSync(path, 'utf8');
if (source.includes('SEP14_WEEK_SWIPE_STABILITY')) process.exit(0);

let next = source;

function replaceRequired(needle, replacement, label) {
  if (!next.includes(needle)) throw new Error(`SEP14 swipe marker changed: ${label}`);
  next = next.replace(needle, replacement);
}

replaceRequired(
  "import './sep13-dienstplan-polish.css';",
  "import './sep13-dienstplan-polish.css';\nimport './sep14-week-swipe-stability.css';",
  'swipe stability css import',
);

replaceRequired(
  `  const swipeFrame = useRef<number | undefined>(undefined);\n  const swipeTravel = useRef(0);`,
  `  const swipeFrame = useRef<number | undefined>(undefined);\n  const swipeTravel = useRef(0);\n  const swipeAxis = useRef<'horizontal' | 'vertical' | null>(null);`,
  'swipe axis ref',
);

replaceRequired(
  `  function changeWeek(delta: number) {\n    setWeekDirection(delta > 0 ? 'next' : 'prev');\n    setAnchor((current) => addDays(current, delta));\n    window.setTimeout(() => setWeekDirection(''), 190);\n  }`,
  `  async function changeWeek(delta: number) {\n    const ionContent = document.querySelector('ion-content.app-content') as any;\n    let scrollElement: HTMLElement | undefined;\n    let savedTop = window.scrollY;\n    try {\n      scrollElement = await ionContent?.getScrollElement?.();\n      if (scrollElement) savedTop = scrollElement.scrollTop;\n    } catch { /* web/native fallback below */ }\n\n    const restoreScroll = () => {\n      if (scrollElement) {\n        scrollElement.scrollTop = savedTop;\n      } else {\n        window.scrollTo({ top: savedTop, left: window.scrollX, behavior: 'auto' });\n      }\n    };\n\n    setWeekDirection(delta > 0 ? 'next' : 'prev');\n    setAnchor((current) => addDays(current, delta));\n\n    // React remounts the center week after the slide. Restore the exact vertical\n    // viewport after layout and once more when the horizontal settle ends. This\n    // prevents Chrome/WebView scroll anchoring from producing a visible jump.\n    window.requestAnimationFrame(() => window.requestAnimationFrame(restoreScroll));\n    window.setTimeout(() => {\n      restoreScroll();\n      setWeekDirection('');\n    }, 190);\n  }`,
  'changeWeek scroll preservation',
);

replaceRequired(
  `            swipe.current = { x: touch.clientX, y: touch.clientY };\n            swipeTravel.current = 0;\n            event.currentTarget.classList.remove('is-dragging', 'is-settling');`,
  `            swipe.current = { x: touch.clientX, y: touch.clientY };\n            swipeTravel.current = 0;\n            swipeAxis.current = null;\n            event.currentTarget.classList.remove('is-dragging', 'is-settling');`,
  'touch start axis reset',
);

replaceRequired(
  `            const dx = touch.clientX - swipe.current.x;\n            const dy = touch.clientY - swipe.current.y;\n            if (Math.abs(dx) < Math.abs(dy) * 1.08) return;\n            swipeTravel.current = dx;\n            const target = event.currentTarget;`,
  `            const dx = touch.clientX - swipe.current.x;\n            const dy = touch.clientY - swipe.current.y;\n            if (!swipeAxis.current && (Math.abs(dx) > 7 || Math.abs(dy) > 7)) {\n              swipeAxis.current = Math.abs(dx) > Math.abs(dy) * 1.12 ? 'horizontal' : 'vertical';\n            }\n            if (swipeAxis.current !== 'horizontal') return;\n            if (event.cancelable) event.preventDefault();\n            swipeTravel.current = dx;\n            const target = event.currentTarget;`,
  'horizontal gesture lock',
);

replaceRequired(
  `            const dx = touch.clientX - swipe.current.x;\n            const dy = touch.clientY - swipe.current.y;\n            swipe.current = undefined;\n            const target = event.currentTarget;`,
  `            const dx = touch.clientX - swipe.current.x;\n            const dy = touch.clientY - swipe.current.y;\n            const axis = swipeAxis.current;\n            swipeAxis.current = null;\n            swipe.current = undefined;\n            const target = event.currentTarget;`,
  'touch end axis capture',
);

replaceRequired(
  `            if (tab !== 'open' && Math.abs(dx) > 44 && Math.abs(dx) > Math.abs(dy) * 1.12) {`,
  `            if (axis === 'horizontal' && tab !== 'open' && Math.abs(dx) > 44 && Math.abs(dx) > Math.abs(dy) * 1.12) {`,
  'horizontal-only week switch',
);

replaceRequired(
  `            swipe.current = undefined;\n            event.currentTarget.classList.add('is-settling');`,
  `            swipe.current = undefined;\n            swipeAxis.current = null;\n            event.currentTarget.classList.add('is-settling');`,
  'touch cancel axis reset',
);

writeFileSync(path, `// SEP14_WEEK_SWIPE_STABILITY\n${next}`);

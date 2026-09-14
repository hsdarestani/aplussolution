import { readFileSync, writeFileSync } from 'node:fs';

const path = new URL('../src/WiwScheduleMobile.tsx', import.meta.url);
const source = readFileSync(path, 'utf8');
if (source.includes('SEP14_WEEK_SWIPE_HANDOFF')) process.exit(0);

let next = source;

function replaceRequired(needle, replacement, label) {
  if (!next.includes(needle)) throw new Error(`SEP14 swipe handoff marker changed: ${label}`);
  next = next.replace(needle, replacement);
}

replaceRequired(
  `import { createPortal } from 'react-dom';`,
  `import { createPortal, flushSync } from 'react-dom';`,
  'react-dom flushSync import',
);

replaceRequired(
  `  async function changeWeek(delta: number) {\n    const ionContent = document.querySelector('ion-content.app-content') as any;\n    let scrollElement: HTMLElement | undefined;\n    let savedTop = window.scrollY;\n    try {\n      scrollElement = await ionContent?.getScrollElement?.();\n      if (scrollElement) savedTop = scrollElement.scrollTop;\n    } catch { /* web/native fallback below */ }\n\n    const restoreScroll = () => {\n      if (scrollElement) {\n        scrollElement.scrollTop = savedTop;\n      } else {\n        window.scrollTo({ top: savedTop, left: window.scrollX, behavior: 'auto' });\n      }\n    };\n\n    setWeekDirection(delta > 0 ? 'next' : 'prev');\n    setAnchor((current) => addDays(current, delta));\n\n    // React remounts the center week after the slide. Restore the exact vertical\n    // viewport after layout and once more when the horizontal settle ends. This\n    // prevents Chrome/WebView scroll anchoring from producing a visible jump.\n    window.requestAnimationFrame(() => window.requestAnimationFrame(restoreScroll));\n    window.setTimeout(() => {\n      restoreScroll();\n      setWeekDirection('');\n    }, 190);\n  }`,
  `  async function changeWeek(delta: number, swipeTrack?: HTMLElement) {\n    const ionContent = document.querySelector('ion-content.app-content') as any;\n    let scrollElement: HTMLElement | undefined;\n    let savedTop = window.scrollY;\n    try {\n      scrollElement = await ionContent?.getScrollElement?.();\n      if (scrollElement) savedTop = scrollElement.scrollTop;\n    } catch { /* web/native fallback below */ }\n\n    const restoreScroll = () => {\n      if (scrollElement) {\n        scrollElement.scrollTop = savedTop;\n      } else {\n        window.scrollTo({ top: savedTop, left: window.scrollX, behavior: 'auto' });\n      }\n    };\n\n    if (swipeTrack) {\n      // At this point the adjacent week is already fully covering the viewport.\n      // Keep it there while getScrollElement resolves, then synchronously swap the\n      // React week and reset the track in the SAME browser paint. Otherwise the\n      // old center week flashes for one frame, which is the visible web jump.\n      swipeTrack.style.transition = 'none';\n      flushSync(() => setAnchor((current) => addDays(current, delta)));\n      swipeTrack.style.setProperty('--wiw-swipe-x', '0px');\n      swipeTrack.classList.remove('is-dragging', 'is-settling');\n      void swipeTrack.offsetWidth;\n      swipeTrack.style.transition = '';\n      restoreScroll();\n    } else {\n      setWeekDirection(delta > 0 ? 'next' : 'prev');\n      setAnchor((current) => addDays(current, delta));\n    }\n\n    window.requestAnimationFrame(() => window.requestAnimationFrame(restoreScroll));\n    window.setTimeout(() => {\n      restoreScroll();\n      if (!swipeTrack) setWeekDirection('');\n    }, 190);\n  }`,
  'atomic week handoff',
);

replaceRequired(
  `              window.setTimeout(() => {\n                changeWeek(dx < 0 ? 7 : -7);\n                target.classList.remove('is-settling');\n                target.style.setProperty('--wiw-swipe-x', '0px');\n              }, 180);`,
  `              window.setTimeout(() => {\n                void changeWeek(dx < 0 ? 7 : -7, target);\n              }, 180);`,
  'touch-end handoff ownership',
);

writeFileSync(path, `// SEP14_WEEK_SWIPE_HANDOFF\n${next}`);

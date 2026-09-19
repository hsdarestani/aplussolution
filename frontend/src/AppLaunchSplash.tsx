import { useEffect, useState } from 'react';
import './app-launch-splash.css';

export function isSplashPreviewMode() {
  if (typeof window === 'undefined') return false;
  return new URLSearchParams(window.location.search).get('splash-preview') === '1';
}

const particles = [
  ['8%', '18%', '-.2s', '2.5s'], ['17%', '43%', '.5s', '2.9s'],
  ['27%', '12%', '.9s', '2.4s'], ['36%', '77%', '.15s', '2.8s'],
  ['47%', '22%', '.65s', '2.6s'], ['58%', '85%', '1.1s', '2.25s'],
  ['67%', '15%', '.3s', '2.75s'], ['77%', '69%', '.8s', '2.35s'],
  ['88%', '28%', '1.2s', '2.65s'], ['93%', '56%', '.1s', '2.85s'],
  ['14%', '90%', '1.05s', '2.35s'], ['33%', '58%', '.55s', '2.55s'],
  ['62%', '46%', '.95s', '2.7s'], ['74%', '92%', '.35s', '2.45s'],
] as const;

export default function AppLaunchSplash() {
  const [phase, setPhase] = useState<'show' | 'hide' | 'done'>('show');
  const preview = isSplashPreviewMode();
  const native = preview || (typeof window !== 'undefined' && Boolean((window as any).Capacitor?.isNativePlatform?.()));

  useEffect(() => {
    if (!native) {
      setPhase('done');
      return;
    }

    let hide = 0;
    let done = 0;
    let replay = 0;

    const play = () => {
      setPhase('show');
      hide = window.setTimeout(() => setPhase('hide'), 2350);
      done = window.setTimeout(() => {
        if (preview) {
          setPhase('done');
          replay = window.setTimeout(play, 650);
        } else {
          setPhase('done');
        }
      }, 2700);
    };

    play();
    return () => {
      window.clearTimeout(hide);
      window.clearTimeout(done);
      window.clearTimeout(replay);
    };
  }, [native, preview]);

  if (!native || phase === 'done') return null;

  return (
    <div className={`app-launch-splash ${phase === 'hide' ? 'is-hiding' : ''}`} aria-hidden="true">
      <div className="app-launch-fog app-launch-fog-one" />
      <div className="app-launch-fog app-launch-fog-two" />

      <svg className="app-launch-ribbons" viewBox="0 0 100 160" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="aplusRibbonGold" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#8e6129" />
            <stop offset=".38" stopColor="#d7a948" />
            <stop offset=".62" stopColor="#ffe7a0" />
            <stop offset=".78" stopColor="#fff6d3" />
            <stop offset="1" stopColor="#9f6b2d" />
          </linearGradient>
          <filter id="aplusRibbonGlow" x="-90%" y="-90%" width="280%" height="280%">
            <feGaussianBlur stdDeviation="1.45" />
          </filter>
        </defs>

        <g className="app-launch-ribbon-glow" filter="url(#aplusRibbonGlow)">
          <path pathLength="1" d="M-8 47 C -2 27, 11 15, 31 7" />
          <path pathLength="1" d="M69 10 C 81 8, 94 7, 110 11" />
          <path pathLength="1" d="M106 58 C 104 73, 107 85, 116 97" />
          <path pathLength="1" d="M108 124 C 100 136, 91 145, 77 153" />
          <path pathLength="1" d="M24 164 C 14 154, 5 147, -10 145" />
          <path pathLength="1" d="M-11 94 C -4 87, 0 80, 1 70" />
        </g>

        <g className="app-launch-ribbon-core">
          <path pathLength="1" d="M-8 47 C -2 27, 11 15, 31 7" />
          <path pathLength="1" d="M69 10 C 81 8, 94 7, 110 11" />
          <path pathLength="1" d="M106 58 C 104 73, 107 85, 116 97" />
          <path pathLength="1" d="M108 124 C 100 136, 91 145, 77 153" />
          <path pathLength="1" d="M24 164 C 14 154, 5 147, -10 145" />
          <path pathLength="1" d="M-11 94 C -4 87, 0 80, 1 70" />
        </g>
      </svg>

      <div className="app-launch-particles">
        {particles.map(([left, top, delay, duration], index) => (
          <span key={index} style={{ left, top, animationDelay: delay, animationDuration: duration }} />
        ))}
      </div>

      <div className="app-launch-logo-stage">
        <div className="app-launch-logo-aura" />
        <img src="/aplus-intro-logo.svg" alt="" draggable={false} />
      </div>
    </div>
  );
}

import { useEffect, useState } from 'react';
import './app-launch-splash.css';

export function isSplashPreviewMode() {
  if (typeof window === 'undefined') return false;
  return new URLSearchParams(window.location.search).get('splash-preview') === '1';
}

const particles = [
  ['10%', '16%', '-.2s', '2.2s'], ['18%', '34%', '.4s', '2.7s'],
  ['28%', '10%', '.8s', '2.4s'], ['39%', '78%', '.2s', '2.8s'],
  ['48%', '18%', '.6s', '2.5s'], ['57%', '86%', '1s', '2.1s'],
  ['66%', '13%', '.3s', '2.7s'], ['76%', '72%', '.7s', '2.3s'],
  ['86%', '27%', '1.1s', '2.6s'], ['92%', '54%', '.1s', '2.9s'],
  ['14%', '88%', '1.2s', '2.3s'], ['33%', '56%', '.5s', '2.6s'],
  ['61%', '43%', '.9s', '2.7s'], ['74%', '91%', '.35s', '2.5s'],
  ['6%', '63%', '.65s', '2.4s'], ['95%', '17%', '.75s', '2.35s'],
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
            <stop offset="0" stopColor="#9b6f31" />
            <stop offset=".45" stopColor="#d9ae55" />
            <stop offset=".72" stopColor="#f5dda2" />
            <stop offset="1" stopColor="#a57131" />
          </linearGradient>
          <filter id="aplusRibbonGlow" x="-70%" y="-70%" width="240%" height="240%">
            <feGaussianBlur stdDeviation=".95" />
          </filter>
        </defs>

        <g className="app-launch-ribbon-glow" filter="url(#aplusRibbonGlow)">
          <path d="M-18 9 C 4 8, 13 17, 15 33 C 17 49, 8 60, -11 71" />
          <path d="M112 23 C 95 23, 89 29, 87 41 C 85 52, 91 61, 111 68" />
          <path d="M-14 126 C 5 124, 14 132, 20 151 C 22 158, 23 164, 22 172" />
          <path d="M112 118 C 96 120, 90 132, 87 148 C 85 157, 84 164, 82 171" />
        </g>

        <g className="app-launch-ribbon-core">
          <path d="M-18 9 C 4 8, 13 17, 15 33 C 17 49, 8 60, -11 71" />
          <path d="M112 23 C 95 23, 89 29, 87 41 C 85 52, 91 61, 111 68" />
          <path d="M-14 126 C 5 124, 14 132, 20 151 C 22 158, 23 164, 22 172" />
          <path d="M112 118 C 96 120, 90 132, 87 148 C 85 157, 84 164, 82 171" />
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

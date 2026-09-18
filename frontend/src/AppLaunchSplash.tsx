import { useEffect, useState } from 'react';
import './app-launch-splash.css';

export function isSplashPreviewMode() {
  if (typeof window === 'undefined') return false;
  return new URLSearchParams(window.location.search).get('splash-preview') === '1';
}

const particles = [
  ['9%', '13%', '-0.2s', '1.9s'],
  ['18%', '31%', '0.35s', '2.4s'],
  ['27%', '8%', '0.8s', '2.1s'],
  ['36%', '73%', '0.15s', '2.5s'],
  ['44%', '18%', '0.55s', '2.2s'],
  ['52%', '83%', '0.95s', '1.8s'],
  ['61%', '11%', '0.25s', '2.4s'],
  ['69%', '69%', '0.65s', '2.0s'],
  ['77%', '24%', '1.05s', '2.3s'],
  ['88%', '52%', '0.1s', '2.6s'],
  ['94%', '17%', '0.7s', '2.1s'],
  ['13%', '88%', '1.1s', '2.0s'],
  ['31%', '53%', '0.45s', '2.3s'],
  ['58%', '42%', '0.9s', '2.4s'],
  ['72%', '91%', '0.3s', '2.2s'],
  ['84%', '78%', '0.75s', '1.9s'],
  ['48%', '5%', '1.2s', '2.5s'],
  ['5%', '61%', '0.6s', '2.1s'],
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
      hide = window.setTimeout(() => setPhase('hide'), 2150);
      done = window.setTimeout(() => {
        if (preview) {
          setPhase('done');
          replay = window.setTimeout(play, 650);
        } else {
          setPhase('done');
        }
      }, 2500);
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
            <stop offset="0" stopColor="#9a6b2d" />
            <stop offset="0.42" stopColor="#e0b75f" />
            <stop offset="0.66" stopColor="#fff0bd" />
            <stop offset="1" stopColor="#b57a30" />
          </linearGradient>
          <filter id="aplusRibbonBloom" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="1.25" />
          </filter>
        </defs>

        <g className="app-launch-ribbon-set app-launch-ribbon-glow" filter="url(#aplusRibbonBloom)">
          <path pathLength="1" d="M-16 4 C 8 5, 30 3, 27 27 C 24 49, 2 58, -8 76 C 9 89, 32 91, 51 103 C 70 115, 86 135, 111 151" />
          <path pathLength="1" d="M-6 24 C 19 24, 39 19, 47 7 C 54 -3, 68 -5, 105 -9" />
          <path pathLength="1" d="M-12 118 C 18 120, 34 110, 39 94 C 44 77, 34 65, 30 51 C 26 36, 39 27, 58 26 C 76 25, 92 20, 112 12" />
          <path pathLength="1" d="M20 171 C 45 151, 58 143, 77 139 C 94 135, 104 126, 113 112" />
        </g>

        <g className="app-launch-ribbon-set app-launch-ribbon-core">
          <path pathLength="1" d="M-16 4 C 8 5, 30 3, 27 27 C 24 49, 2 58, -8 76 C 9 89, 32 91, 51 103 C 70 115, 86 135, 111 151" />
          <path pathLength="1" d="M-6 24 C 19 24, 39 19, 47 7 C 54 -3, 68 -5, 105 -9" />
          <path pathLength="1" d="M-12 118 C 18 120, 34 110, 39 94 C 44 77, 34 65, 30 51 C 26 36, 39 27, 58 26 C 76 25, 92 20, 112 12" />
          <path pathLength="1" d="M20 171 C 45 151, 58 143, 77 139 C 94 135, 104 126, 113 112" />
        </g>
      </svg>

      <div className="app-launch-particles">
        {particles.map(([left, top, delay, duration], index) => (
          <span
            key={index}
            style={{ left, top, animationDelay: delay, animationDuration: duration }}
          />
        ))}
      </div>

      <div className="app-launch-logo-stage">
        <div className="app-launch-logo-aura" />
        <img src="/aplus-intro-logo.svg" alt="" />
        <span className="app-launch-logo-shine" />
      </div>
    </div>
  );
}

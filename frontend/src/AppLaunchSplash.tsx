import { useEffect, useState } from 'react';
import './app-launch-splash.css';

export function isSplashPreviewMode() {
  if (typeof window === 'undefined') return false;
  return new URLSearchParams(window.location.search).get('splash-preview') === '1';
}

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
      hide = window.setTimeout(() => setPhase('hide'), 1350);
      done = window.setTimeout(() => {
        if (preview) {
          setPhase('done');
          replay = window.setTimeout(play, 520);
        } else {
          setPhase('done');
        }
      }, 1720);
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
      <div className="app-launch-glow app-launch-glow-one" />
      <div className="app-launch-glow app-launch-glow-two" />
      <div className="app-launch-logo-wrap">
        <span className="app-launch-ring ring-one" />
        <span className="app-launch-ring ring-two" />
        <img src="/5.png" alt="" />
      </div>
      <strong>A+ SOLUTION GMBH</strong>
      <small>Alles organisiert. Alles im Griff.</small>
      <div className="app-launch-progress"><i /></div>
    </div>
  );
}

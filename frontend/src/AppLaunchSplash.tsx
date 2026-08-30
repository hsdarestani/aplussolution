import { useEffect, useState } from 'react';
import './app-launch-splash.css';

export default function AppLaunchSplash() {
  const [phase, setPhase] = useState<'show' | 'hide' | 'done'>('show');
  const native = typeof window !== 'undefined' && Boolean((window as any).Capacitor?.isNativePlatform?.());

  useEffect(() => {
    if (!native) {
      setPhase('done');
      return;
    }
    const hide = window.setTimeout(() => setPhase('hide'), 1350);
    const done = window.setTimeout(() => setPhase('done'), 1720);
    return () => {
      window.clearTimeout(hide);
      window.clearTimeout(done);
    };
  }, [native]);

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

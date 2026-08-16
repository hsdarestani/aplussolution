import React, { useEffect } from 'react';
import SelfServiceDock from './SelfServiceDock';
import './self-service-v10-compat.css';

export default function SelfServiceDockMount() {
  useEffect(() => {
    const normalizeLauncherName = () => {
      const launcher = document.querySelector<HTMLElement>('[data-testid="self-service-launcher"]');
      if (!launcher) return false;
      launcher.setAttribute('aria-label', 'Self-Service');
      return true;
    };

    if (normalizeLauncherName()) return undefined;
    const observer = new MutationObserver(() => {
      if (normalizeLauncherName()) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return <SelfServiceDock />;
}

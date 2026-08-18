import React from 'react';
import ReactDOM from 'react-dom/client';
import { setupIonicReact } from '@ionic/react';
import { registerSW } from 'virtual:pwa-register';
import '@ionic/react/css/core.css';
import '@ionic/react/css/normalize.css';
import '@ionic/react/css/structure.css';
import '@ionic/react/css/typography.css';
import '@ionic/react/css/padding.css';
import './theme.css';
import './brand-refresh.css';
import App from './App';
import StoreComplianceLinks from './StoreComplianceLinks';
import StoreLegalPage, { legalPageFromPath } from './StoreLegalPages';

setupIonicReact({ mode: 'md' });

// Keep the installed PWA/app shell in sync with the latest production build.
// A previous generated service worker could keep serving an old precached
// index after a normal refresh while a hard refresh bypassed it. Registering
// explicitly and checking on startup/focus makes updates deterministic.
let updateSW: ((reloadPage?: boolean) => Promise<void>) | undefined;
updateSW = registerSW({
  immediate: true,
  onNeedRefresh() {
    void updateSW?.(true);
  },
  onRegisteredSW(_swUrl, registration) {
    if (!registration) return;

    const checkForUpdate = () => {
      void registration.update().catch(() => {
        // Network failures should never block app startup.
      });
    };

    checkForUpdate();
    window.addEventListener('focus', checkForUpdate);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') checkForUpdate();
    });
  },
});

const legalPage = legalPageFromPath(window.location.pathname);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {legalPage ? (
      <StoreLegalPage page={legalPage} />
    ) : (
      <>
        <App />
        <StoreComplianceLinks />
      </>
    )}
  </React.StrictMode>,
);

import React from 'react';
import ReactDOM from 'react-dom/client';
import { setupIonicReact } from '@ionic/react';
import '@ionic/react/css/core.css';
import '@ionic/react/css/normalize.css';
import '@ionic/react/css/structure.css';
import '@ionic/react/css/typography.css';
import '@ionic/react/css/padding.css';
import './theme.css';
import './brand-refresh.css';
import './people-lists.css';
import './steuerzentrale-hardening.css';
import './header-quick-access.css';
import './mobile-header-actions-fix.css';
import './phase8-wiw-mobile.css';
import './wiw-mobile-light.css';
import './schedule-month-compact.css';
import App from './App';
import StoreComplianceLinks from './StoreComplianceLinks';
import StoreLegalPage, { legalPageFromPath } from './StoreLegalPages';
import FriendlyDateTimePicker from './FriendlyDateTimePicker';
import PayrollWorkspaceEnhancer from './PayrollWorkspaceEnhancer';
import WorkflowCompletionEnhancer from './WorkflowCompletionEnhancer';
import ApiHealthBanner from './ApiHealthBanner';
import HeaderQuickAccess from './HeaderQuickAccess';
import ScheduleMobileEnhancer from './ScheduleMobileEnhancer';
import NativePushRegistration from './NativePushRegistration';
import { installBerlinLocaleDefaults } from './berlinLocale';
import { installOperationalFetchResilience } from './operationalFetchResilience';
import { installLocationPicker } from './locationPicker';
import { installMobileAppearance } from './mobileAppearance';

installBerlinLocaleDefaults();
installOperationalFetchResilience();
installLocationPicker();
installMobileAppearance();
setupIonicReact({ mode: 'md' });

function renderApp() {
  const legalPage = legalPageFromPath(window.location.pathname);

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      {legalPage ? (
        <StoreLegalPage page={legalPage} />
      ) : (
        <>
          <App />
          <HeaderQuickAccess />
          <ScheduleMobileEnhancer />
          <NativePushRegistration />
          <StoreComplianceLinks />
          <FriendlyDateTimePicker />
          <PayrollWorkspaceEnhancer />
          <WorkflowCompletionEnhancer />
          <ApiHealthBanner />
        </>
      )}
    </React.StrictMode>,
  );
}

async function retireLegacyPwa() {
  if (!('serviceWorker' in navigator)) return false;

  try {
    const registrations = await navigator.serviceWorker.getRegistrations();
    const hadController = Boolean(navigator.serviceWorker.controller);

    await Promise.all(registrations.map((registration) => registration.unregister()));

    if ('caches' in window) {
      const keys = await caches.keys();
      await Promise.all(keys.map((key) => caches.delete(key));
    }

    // unregister() does not release the controller from the current page. Reload
    // exactly once after clearing caches so the next navigation is network-only.
    if ((registrations.length > 0 || hadController) && sessionStorage.getItem('legacy-sw-cleanup-reload') !== '1') {
      sessionStorage.setItem('legacy-sw-cleanup-reload', '1');
      window.location.reload();
      return true;
    }

    sessionStorage.removeItem('legacy-sw-cleanup-reload');
  } catch {
    // A cleanup failure must never prevent the login screen from rendering.
  }

  return false;
}

void retireLegacyPwa().then((reloading) => {
  if (!reloading) renderApp();
});
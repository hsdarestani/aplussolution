import React, { useEffect, useRef, useState } from 'react';
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
import ClientPortalV2 from './ClientPortalV2';
import StoreComplianceLinks from './StoreComplianceLinks';
import StoreLegalPage, { legalPageFromPath } from './StoreLegalPages';
import FriendlyDateTimePicker from './FriendlyDateTimePicker';
import PayrollWorkspaceEnhancer from './PayrollWorkspaceEnhancer';
import WorkflowCompletionEnhancer from './WorkflowCompletionEnhancer';
import OrderDocumentImportEnhancer from './OrderDocumentImportEnhancer';
import ApiHealthBanner from './ApiHealthBanner';
import HeaderQuickAccess from './HeaderQuickAccess';
import ScheduleMobileEnhancer from './ScheduleMobileEnhancer';
import ScheduleEntryFilterEnhancer from './ScheduleEntryFilterEnhancer';
import SchedulePdfLocationFilter from './SchedulePdfLocationFilter';
import WiwScheduleMobile from './WiwScheduleMobile';
import WiwEmployeeScheduleMobile from './WiwEmployeeScheduleMobile';
import ClientPortalVisualParity from './ClientPortalVisualParity';
import WiwShiftFormUxEnhancer from './WiwShiftFormUxEnhancer';
import WiwShiftKeyboardGuard from './WiwShiftKeyboardGuard';
import WiwWorkerPickerEligibilityEnhancer from './WiwWorkerPickerEligibilityEnhancer';
import ShiftReleaseApprovalPanel from './ShiftReleaseApprovalPanel';
import AdminScheduleTools from './AdminScheduleTools';
import AdminAvailabilityManager from './AdminAvailabilityManager';
import AdminClientRequestPanel from './AdminClientRequestPanel';
import CheckoutReviewEnhancer from './CheckoutReviewEnhancer';
import DesktopAttendanceHistoryEnhancer from './DesktopAttendanceHistoryEnhancer';
import MobileAttendanceClarityEnhancer from './MobileAttendanceClarityEnhancer';
import MobileOperationsSectionMenu from './MobileOperationsSectionMenu';
import NativePushRegistration from './NativePushRegistration';
import AppLaunchSplash, { isSplashPreviewMode } from './AppLaunchSplash';
import SelfProfileAvatarEnhancer from './SelfProfileAvatarEnhancer';
import AdminAkteAvatarEnhancer from './AdminAkteAvatarEnhancer';
import { installBerlinLocaleDefaults } from './berlinLocale';
import { installOperationalFetchResilience } from './operationalFetchResilience';
import { installSignaturePad } from './signaturePad';
import { installLocationPicker } from './locationPicker';
import { installMobileAppearance } from './mobileAppearance';
import './brand-navy.css';
import './mobile-readable-typography.css';
import './mobile-page-gutters.css';
import './wiw-shift-save-hotfix.css';
import './wiw-client-divider-polish.css';
import './schedule-desktop-polish.css';
import './wiw-mobile-20260902.css';
import './mobile-schedule-filter-removal.css';
import './wiw-ios-date-note-polish.css';
import './wiw-mobile-overlay-stability.css';
import './schedule-client-exact-colors.css';
import './wiw-schedule-bottom-clearance.css';
import './wiw-shift-keyboard-guard.css';

installBerlinLocaleDefaults();
installOperationalFetchResilience();
installSignaturePad();
installLocationPicker();
installMobileAppearance();
setupIonicReact({ mode: 'md' });

/*
 * Client portal enhancers historically inspected localStorage only once when the
 * application mounted. On a fresh login they therefore mounted before the access
 * token existed and stayed dormant until the browser was manually refreshed.
 * Keep them keyed to the current auth session so a token created/removed in this
 * tab remounts the enhancers without reloading the page.
 */
function ClientPortalMount() {
  const [generation, setGeneration] = useState(0);
  const tokenRef = useRef<string | null>(null);

  useEffect(() => {
    tokenRef.current = localStorage.getItem('access');
    const syncSession = () => {
      const nextToken = localStorage.getItem('access');
      if (nextToken === tokenRef.current) return;
      tokenRef.current = nextToken;
      setGeneration((value) => value + 1);
    };

    const timer = window.setInterval(syncSession, 180);
    window.addEventListener('storage', syncSession);
    window.addEventListener('focus', syncSession);
    window.addEventListener('pageshow', syncSession);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('storage', syncSession);
      window.removeEventListener('focus', syncSession);
      window.removeEventListener('pageshow', syncSession);
    };
  }, []);

  return <React.Fragment key={generation}>
    <ClientPortalV2 />
    <ClientPortalVisualParity />
  </React.Fragment>;
}

function ResumeAwareEnhancers() {
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    const resume = () => setGeneration((value) => value + 1);
    window.addEventListener('aplus-app-resume', resume);
    return () => window.removeEventListener('aplus-app-resume', resume);
  }, []);

  // Keep the manager/admin mobile Dienstplan mounted across app resume.
  // Remounting this surface used to briefly (and sometimes persistently) expose
  // the legacy ScheduleV2 underneath until the user changed tabs.
  return <>
    <WiwScheduleMobile />
    <React.Fragment key={generation}>
    <ClientPortalMount />
    <HeaderQuickAccess />
    <ScheduleMobileEnhancer />
    <ScheduleEntryFilterEnhancer />
    <SchedulePdfLocationFilter />
    <WiwEmployeeScheduleMobile />
    <WiwShiftFormUxEnhancer />
    <WiwShiftKeyboardGuard />
    <WiwWorkerPickerEligibilityEnhancer />
    <ShiftReleaseApprovalPanel />
    <AdminScheduleTools />
    <AdminAvailabilityManager />
    <AdminClientRequestPanel />
    <CheckoutReviewEnhancer />
    <DesktopAttendanceHistoryEnhancer />
    <MobileAttendanceClarityEnhancer />
    <MobileOperationsSectionMenu />
    <NativePushRegistration />
    <SelfProfileAvatarEnhancer />
    <AdminAkteAvatarEnhancer />
    <StoreComplianceLinks />
    <FriendlyDateTimePicker />
    <PayrollWorkspaceEnhancer />
    <WorkflowCompletionEnhancer />
    <OrderDocumentImportEnhancer />
    <ApiHealthBanner />
    </React.Fragment>
  </>;
}

function renderApp() {
  const splashPreview = isSplashPreviewMode();
  const legalPage = legalPageFromPath(window.location.pathname);

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      {splashPreview ? (
        <AppLaunchSplash />
      ) : legalPage ? (
        <StoreLegalPage page={legalPage} />
      ) : (
        <>
          <AppLaunchSplash />
          <App />
          <ResumeAwareEnhancers />
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
      await Promise.all(keys.map((key) => caches.delete(key)));
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

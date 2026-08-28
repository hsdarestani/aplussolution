import { useEffect, useRef } from 'react';

const ENTRY_FILTER_KEY = 'aplus:schedule-entry-filter';

/**
 * Keeps the core ScheduleV2 state aligned with the navigation intent on every
 * form factor. Mobile managers get the WIW overlay, but desktop managers still
 * use ScheduleV2 directly, so the same default/filter rule must exist there.
 */
export default function ScheduleEntryFilterEnhancer() {
  const initialized = useRef(false);

  useEffect(() => {
    const rememberOpenShiftIntent = (event: Event) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest('[aria-label="OpenShifts verfügbar"]')) {
        sessionStorage.setItem(ENTRY_FILTER_KEY, 'open');
      }
    };
    document.addEventListener('click', rememberOpenShiftIntent, true);

    const sync = () => {
      const schedule = document.querySelector('.mobile-first-app-shell-v1[data-view="schedule"]');
      if (!schedule) {
        initialized.current = false;
        return;
      }
      if (initialized.current) return;

      const segment = schedule.querySelector<HTMLElement>('.sv2 > ion-segment');
      if (!segment) return;
      const requested = sessionStorage.getItem(ENTRY_FILTER_KEY);
      const targetValue = requested === 'open' ? 'open' : 'all';
      const button = segment.querySelector<HTMLElement>(`ion-segment-button[value="${targetValue}"]`);
      if (!button) return;

      initialized.current = true;
      sessionStorage.removeItem(ENTRY_FILTER_KEY);
      window.setTimeout(() => button.click(), 0);
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    return () => {
      observer.disconnect();
      document.removeEventListener('click', rememberOpenShiftIntent, true);
    };
  }, []);

  return null;
}

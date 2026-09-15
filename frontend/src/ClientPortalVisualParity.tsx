import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, User } from './api';
import { ClientRatingsMobile } from './ClientPortalMobileViews';
import ClientScheduleWorkforceMobile from './ClientScheduleWorkforceMobile';
import './client-portal-visual-parity.css';
import './client-portal-brand-preserve.css';
import './client-portal-modal-fix.css';

export default function ClientPortalVisualParity() {
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState('dashboard');
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches);
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!localStorage.getItem('access')) return;
    void api('auth/me/').then((current: User) => {
      if (!cancelled && current?.role === 'client') setUser(current);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)');
    const sync = () => setMobile(media.matches);
    sync();
    media.addEventListener?.('change', sync);
    return () => media.removeEventListener?.('change', sync);
  }, []);

  useEffect(() => {
    if (!user) return;
    const sync = () => {
      const shell = document.querySelector<HTMLElement>('.mobile-first-app-shell-v1');
      setView(shell?.dataset.view || 'dashboard');
      setHost(document.querySelector<HTMLElement>('.app-main'));
    };
    sync();
    const root = document.getElementById('root');
    const observer = new MutationObserver(sync);
    if (root) observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    return () => observer.disconnect();
  }, [user]);

  useEffect(() => {
    const custom = Boolean(user && mobile && (view === 'schedule' || view === 'ratings'));
    const schedule = Boolean(custom && view === 'schedule');
    document.body.classList.toggle('client-v3-custom-view', custom);
    document.body.classList.toggle('client-v3-ratings-active', custom && view === 'ratings');
    // Reuse the exact body state used by the working employee schedule. Do not
    // activate the old client/admin schedule viewport overrides here.
    document.body.classList.toggle('wiw-employee-schedule-active', schedule);
    document.body.classList.remove('client-v3-schedule-active', 'wiw-native-schedule-active');
    return () => {
      document.body.classList.remove(
        'client-v3-custom-view',
        'client-v3-ratings-active',
        'client-v3-schedule-active',
        'wiw-native-schedule-active',
        'wiw-employee-schedule-active',
      );
    };
  }, [mobile, user, view]);

  // The legacy client schedule remains mounted underneath App. Retire only its
  // QA hooks while this workforce calendar is active so the visible schedule owns
  // the same stable selectors as Admin/Mitarbeiter.
  useEffect(() => {
    if (!user || !mobile || view !== 'schedule') return;
    const legacy = Array.from(document.querySelectorAll<HTMLElement>(
      '.sv2 [data-testid="phase8-week-strip"], .sv2 [data-testid="schedule-day-view"], .sv2 [data-testid="phase8-week-total"]',
    ));
    const retired = legacy.map((element) => ({ element, testId: element.getAttribute('data-testid') }));
    legacy.forEach((element) => element.removeAttribute('data-testid'));
    return () => {
      retired.forEach(({ element, testId }) => {
        if (element.isConnected && testId) element.setAttribute('data-testid', testId);
      });
    };
  }, [mobile, user, view]);

  if (!user || !mobile || !host) return null;
  if (view === 'schedule') return createPortal(<ClientScheduleWorkforceMobile />, host);
  if (view === 'ratings') return createPortal(<ClientRatingsMobile />, host);
  return null;
}

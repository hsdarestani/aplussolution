import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, User } from './api';
import {
  ClientDocumentsMobile,
  ClientOrdersMobile,
  ClientRatingsMobileV4,
  RestrictedClientGate,
  type ClientAccess,
} from './ClientPortalMobileV4';
import ClientScheduleWorkforceMobile from './ClientScheduleWorkforceMobile';
import './client-portal-visual-parity.css';
import './client-portal-brand-preserve.css';
import './client-portal-modal-fix.css';
import './client-portal-v4.css';
import './client-workforce-schedule.css';

export default function ClientPortalVisualParity() {
  const [user, setUser] = useState<User | null>(null);
  const [access, setAccess] = useState<ClientAccess | null>(null);
  const [view, setView] = useState('dashboard');
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches);
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!localStorage.getItem('access')) return;
    void Promise.all([api('auth/me/'), api('portal/client-access/')]).then(([current, portalAccess]: any[]) => {
      if (!cancelled && current?.role === 'client') {
        setUser(current);
        setAccess(portalAccess);
      }
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
    const schedule = Boolean(user && mobile && view === 'schedule');
    const customView = Boolean(
      user && mobile && (
        ['ratings', 'orders', 'documents'].includes(view)
        || (access?.read_only && view !== 'dashboard' && view !== 'schedule')
      )
    );

    document.body.classList.toggle('wiw-employee-schedule-active', schedule);
    document.body.classList.toggle('client-v3-custom-view', customView);
    document.body.classList.toggle('client-v3-ratings-active', customView && view === 'ratings');
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
  }, [mobile, user, access?.read_only, view]);

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

  if (!user || !access || !mobile || !host) return null;
  if (view === 'schedule') return createPortal(<ClientScheduleWorkforceMobile />, host);
  if (access.read_only && view !== 'dashboard') return createPortal(<RestrictedClientGate access={access} />, host);
  if (view === 'ratings') return createPortal(<ClientRatingsMobileV4 access={access} />, host);
  if (view === 'orders') return createPortal(<ClientOrdersMobile access={access} />, host);
  if (view === 'documents') return createPortal(<ClientDocumentsMobile access={access} />, host);
  return null;
}

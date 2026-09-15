import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, User } from './api';
import { ClientRatingsMobile, ClientScheduleMobile } from './ClientPortalMobileViews';
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
    document.body.classList.toggle('client-v3-custom-view', custom);
    document.body.classList.toggle('client-v3-schedule-active', custom && view === 'schedule');
    document.body.classList.toggle('client-v3-ratings-active', custom && view === 'ratings');
    if (custom && view === 'schedule') document.body.classList.add('wiw-native-schedule-active');
    else document.body.classList.remove('wiw-native-schedule-active');
    return () => {
      document.body.classList.remove('client-v3-custom-view', 'client-v3-schedule-active', 'client-v3-ratings-active');
      if (user?.role === 'client') document.body.classList.remove('wiw-native-schedule-active');
    };
  }, [mobile, user, view]);

  // Keep the same stable schedule hooks as employee/admin while the legacy client
  // schedule remains mounted underneath. Loading data can replace parts of either
  // tree, so keep the hook hand-off synchronized for the lifetime of this view.
  useEffect(() => {
    if (!user || !mobile || view !== 'schedule') return;

    const root = document.getElementById('root');
    const retired = new Map<HTMLElement, string>();
    const legacySelector = '.sv2 [data-testid="phase8-week-strip"], .sv2 [data-testid="schedule-day-view"], .sv2 [data-testid="phase8-week-total"]';

    const applyHooks = () => {
      document.querySelectorAll<HTMLElement>(legacySelector).forEach((element) => {
        const testId = element.getAttribute('data-testid');
        if (!testId) return;
        retired.set(element, testId);
        element.removeAttribute('data-testid');
      });

      const weekStrip = document.querySelector<HTMLElement>('.client-v3-week-strip');
      const dayView = document.querySelector<HTMLElement>('.client-v3-week-scroll');
      const weekTotal = document.querySelector<HTMLElement>('.client-v3-week-total');
      weekStrip?.setAttribute('data-testid', 'phase8-week-strip');
      dayView?.setAttribute('data-testid', 'schedule-day-view');
      dayView?.setAttribute('data-layout', 'list');
      weekTotal?.setAttribute('data-testid', 'phase8-week-total');
    };

    applyHooks();
    const observer = new MutationObserver(applyHooks);
    if (root) observer.observe(root, { subtree: true, childList: true });

    return () => {
      observer.disconnect();
      const weekStrip = document.querySelector<HTMLElement>('.client-v3-week-strip');
      const dayView = document.querySelector<HTMLElement>('.client-v3-week-scroll');
      const weekTotal = document.querySelector<HTMLElement>('.client-v3-week-total');
      weekStrip?.setAttribute('data-testid', 'client-v3-week-strip');
      dayView?.setAttribute('data-testid', 'client-v3-schedule-days');
      dayView?.removeAttribute('data-layout');
      weekTotal?.removeAttribute('data-testid');
      retired.forEach((testId, element) => {
        if (element.isConnected) element.setAttribute('data-testid', testId);
      });
    };
  }, [mobile, user, view]);

  if (!user || !mobile || !host) return null;
  if (view === 'schedule') return createPortal(<ClientScheduleMobile />, host);
  if (view === 'ratings') return createPortal(<ClientRatingsMobile />, host);
  return null;
}

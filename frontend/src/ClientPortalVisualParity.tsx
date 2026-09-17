import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, User } from './api';
import {
  ClientDocumentsMobile,
  ClientOrdersMobile,
  ClientRatingsMobileV4,
  ClientScheduleMobileV4,
  RestrictedClientGate,
  type ClientAccess,
} from './ClientPortalMobileV4';
import './client-portal-visual-parity.css';
import './client-portal-brand-preserve.css';
import './client-portal-modal-fix.css';
import './client-portal-v4.css';

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
    const customViews = new Set(['schedule', 'ratings', 'orders', 'documents']);
    const restrictedOverlay = Boolean(access?.read_only && view !== 'dashboard' && view !== 'schedule');
    const active = Boolean(user && mobile && (customViews.has(view) || restrictedOverlay));
    document.body.classList.toggle('client-v3-custom-view', active);
    document.body.classList.toggle('client-v3-ratings-active', active && view === 'ratings');
    document.body.classList.toggle('client-v3-schedule-active', active && view === 'schedule');
    document.body.classList.remove('wiw-native-schedule-active', 'wiw-employee-schedule-active');
    return () => document.body.classList.remove('client-v3-custom-view', 'client-v3-ratings-active', 'client-v3-schedule-active');
  }, [mobile, user, access?.read_only, view]);

  if (!user || !access || !mobile || !host) return null;
  if (view === 'schedule') return createPortal(<ClientScheduleMobileV4 access={access} />, host);
  if (access.read_only && view !== 'dashboard') return createPortal(<RestrictedClientGate access={access} />, host);
  if (view === 'ratings') return createPortal(<ClientRatingsMobileV4 access={access} />, host);
  if (view === 'orders') return createPortal(<ClientOrdersMobile access={access} />, host);
  if (view === 'documents') return createPortal(<ClientDocumentsMobile access={access} />, host);
  return null;
}

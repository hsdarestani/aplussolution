import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, User } from './api';
import { ClientRatingsMobile, ClientScheduleMobile } from './ClientPortalMobileViews';
import './client-portal-visual-parity.css';

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

  if (!user || !mobile || !host) return null;
  if (view === 'schedule') return createPortal(<ClientScheduleMobile />, host);
  if (view === 'ratings') return createPortal(<ClientRatingsMobile />, host);
  return null;
}

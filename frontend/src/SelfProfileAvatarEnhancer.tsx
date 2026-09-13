import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from './api';
import ProfileAvatarUpload from './ProfileAvatarUpload';

export default function SelfProfileAvatarEnhancer() {
  const [host, setHost] = useState<Element | null>(null);
  const [user, setUser] = useState<any>();

  useEffect(() => {
    const locate = () => {
      const shell = document.querySelector('.mobile-first-app-shell-v1[data-view="profile"]');
      const next = shell?.querySelector('.app-main') || shell;
      setHost(next || null);
    };
    locate();
    const observer = new MutationObserver(locate);
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-view'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!host) { setUser(undefined); return; }
    let cancelled = false;
    void api('auth/me/').then((result: any) => { if (!cancelled) setUser(result); }).catch(() => setUser(undefined));
    return () => { cancelled = true; };
  }, [host]);

  if (!host || user?.role !== 'worker') return null;
  return createPortal(
    <div className="profile-avatar-self-host" data-testid="self-profile-avatar-upload">
      <ProfileAvatarUpload avatar={user.avatar} name={user.name || user.email || 'Mitarbeiter'} onUploaded={setUser} />
    </div>,
    host,
  );
}

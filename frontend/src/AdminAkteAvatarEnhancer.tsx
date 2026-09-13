import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import ProfileAvatarUpload from './ProfileAvatarUpload';

function currentWorkerId() {
  const params = new URLSearchParams(window.location.search);
  return params.get('akte_kind') === 'worker' ? params.get('akte_id') || '' : '';
}

export default function AdminAkteAvatarEnhancer() {
  const [host, setHost] = useState<Element | null>(null);
  const [workerId, setWorkerId] = useState('');
  const [name, setName] = useState('Mitarbeiter');

  useEffect(() => {
    const locate = () => {
      const id = currentWorkerId();
      const hero = id ? document.querySelector('.akte-page .akte-hero') : null;
      setWorkerId(id);
      setHost(hero);
      setName(hero?.querySelector('h1')?.textContent?.trim() || 'Mitarbeiter');
    };
    locate();
    const observer = new MutationObserver(locate);
    observer.observe(document.body, { subtree: true, childList: true });
    window.addEventListener('popstate', locate);
    return () => {
      observer.disconnect();
      window.removeEventListener('popstate', locate);
    };
  }, []);

  if (!host || !workerId) return null;
  return createPortal(
    <ProfileAvatarUpload workerId={workerId} name={name} compact />,
    host,
  );
}

import React, { useRef, useState } from 'react';
import { api } from './api';
import './profile-avatar-upload.css';

type Props = {
  workerId?: string;
  avatar?: string;
  name?: string;
  compact?: boolean;
  onUploaded?: (user: any) => void;
};

export default function ProfileAvatarUpload({ workerId, avatar, name = 'Mitarbeiter', compact = false, onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [currentAvatar, setCurrentAvatar] = useState(avatar || '');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  async function upload(file?: File) {
    if (!file || busy) return;
    setBusy(true);
    setMessage('');
    const body = new FormData();
    body.append('avatar', file);
    if (workerId) body.append('worker_id', workerId);
    try {
      const result: any = await api('auth/profile/avatar/', { method: 'POST', body });
      setCurrentAvatar(String(result?.avatar || ''));
      setMessage('Profilbild gespeichert.');
      onUploaded?.(result);
    } catch (error: any) {
      setMessage(error?.message || 'Profilbild konnte nicht gespeichert werden.');
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  return <div className={`profile-avatar-upload ${compact ? 'compact' : ''}`}>
    <div className="profile-avatar-upload-image">
      {currentAvatar ? <img src={currentAvatar} alt={`Profilbild ${name}`} /> : <span>{name.trim().split(/\s+/).slice(0, 2).map(part => part[0] || '').join('').toUpperCase() || 'MA'}</span>}
    </div>
    <div className="profile-avatar-upload-copy">
      {!compact ? <><b>Profilbild</b><small>JPG, PNG oder WebP · maximal 5 MB</small></> : null}
      <button type="button" disabled={busy} onClick={() => inputRef.current?.click()}>{busy ? 'Wird geladen …' : currentAvatar ? 'Foto ändern' : 'Foto hochladen'}</button>
      <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={event => void upload(event.target.files?.[0])} />
      {message ? <em>{message}</em> : null}
    </div>
  </div>;
}

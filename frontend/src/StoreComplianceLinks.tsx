import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import './store-compliance.css';

type Targets = { login: Element | null; profile: Element | null };

function Links({ profile = false }: { profile?: boolean }) {
  return (
    <div className={`store-compliance-links${profile ? ' store-compliance-profile' : ''}`}>
      {!profile && (
        <>
          <span className="store-internal-badge">Interner Unternehmenszugang</span>
          <p>Keine öffentliche Registrierung. Konten werden ausschließlich durch A+ Solution angelegt oder persönlich eingeladen.</p>
        </>
      )}
      {profile && <p>Datenschutz, Support und Informationen zur Löschung deines App-Zugangs.</p>}
      <nav aria-label="Datenschutz und Support">
        <a href="/datenschutz">Datenschutz</a>
        <a href="/konto-loeschen">Kontolöschung</a>
        <a href="/impressum">Impressum</a>
        <a href="/support">Support</a>
      </nav>
    </div>
  );
}

export default function StoreComplianceLinks() {
  const [targets, setTargets] = useState<Targets>({ login: null, profile: null });

  useEffect(() => {
    const findTargets = () => {
      const login = document.querySelector('.login-card');
      const profile = document.querySelector('.profile-grid .panel.profile');
      setTargets((current) =>
        current.login === login && current.profile === profile ? current : { login, profile },
      );
    };
    findTargets();
    const observer = new MutationObserver(findTargets);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return (
    <>
      {targets.login ? createPortal(<Links />, targets.login) : null}
      {targets.profile ? createPortal(<Links profile />, targets.profile) : null}
    </>
  );
}

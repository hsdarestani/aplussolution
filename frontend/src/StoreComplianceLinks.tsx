import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import './store-compliance.css';

type Targets = { login: Element | null; profile: Element | null; attendance: Element | null };

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

function LocationDisclosure() {
  return (
    <div className="store-compliance-links">
      <strong>Standort bei der Zeiterfassung</strong>
      <p>
        Beim Ein- oder Ausstempeln wird dein aktueller präziser Standort einmalig erfasst, um den vorgesehenen
        Einsatzort zu prüfen. Es findet keine Hintergrundortung oder werbliche Standortverfolgung statt.
      </p>
      <nav aria-label="Standort-Datenschutz">
        <a href="/datenschutz">Details zum Datenschutz</a>
      </nav>
    </div>
  );
}

export default function StoreComplianceLinks() {
  const [targets, setTargets] = useState<Targets>({ login: null, profile: null, attendance: null });

  useEffect(() => {
    const findTargets = () => {
      const login = document.querySelector('.login-card');
      const profile = document.querySelector('.profile-grid .panel.profile');
      const clockButton = Array.from(document.querySelectorAll('ion-button')).find((element) =>
        /Einstempeln|Arbeitszeit starten/i.test(element.textContent || ''),
      );
      const attendance = clockButton ? document.querySelector('.attendance-head') : null;
      setTargets((current) =>
        current.login === login && current.profile === profile && current.attendance === attendance
          ? current
          : { login, profile, attendance },
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
      {targets.attendance ? createPortal(<LocationDisclosure />, targets.attendance) : null}
    </>
  );
}

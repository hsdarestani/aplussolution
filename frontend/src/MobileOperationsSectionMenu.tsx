import React, { useEffect, useMemo, useState } from 'react';
import './mobile-operations-section-menu.css';

const MOBILE_QUERY = '(max-width: 767px)';

const HIDDEN_ON_MOBILE = new Set([
  'Schichtkonflikte',
  'Verfügbarkeit',
  'Stundenrisiken',
  'A+ Workforce Datenbasis',
  'Produktionsbereitschaft',
  'Digitale Akten',
]);

const SECTION_ORDER = [
  'Personalabdeckung',
  'Schichttausch freigeben',
  'Planungswerkzeuge',
  'Berichte & Exporte',
  'Arbeitszeitkonto',
  'Auftragsautomation & ANÜ',
  '8 Dokumentmodelle',
  'WIW Migration / Altbestand',
  'Erweiterte Workforce-Steuerung',
  'Benachrichtigungen',
];

const SHORT_LABELS: Record<string, string> = {
  'Personalabdeckung': 'Personal',
  'Schichttausch freigeben': 'Schichttausch',
  'Planungswerkzeuge': 'Planung',
  'Berichte & Exporte': 'Berichte',
  'Arbeitszeitkonto': 'Arbeitszeit',
  'Auftragsautomation & ANÜ': 'Aufträge & ANÜ',
  '8 Dokumentmodelle': 'Dokumente',
  'WIW Migration / Altbestand': 'WIW',
  'Erweiterte Workforce-Steuerung': 'Workforce Pro',
  'Benachrichtigungen': 'Mitteilungen',
};

function panelTitle(panel: HTMLElement) {
  return panel.querySelector<HTMLElement>('h3')?.textContent?.trim() || '';
}

function operationsPanels() {
  return Array.from(document.querySelectorAll<HTMLElement>('.operations-panel'));
}

function findOperationsContext() {
  const panels = operationsPanels();
  const titles = new Set(panels.map(panelTitle));
  const managerPage = titles.has('Planungswerkzeuge') || titles.has('Personalabdeckung');
  return { panels, managerPage };
}

function updateGridVisibility() {
  document.querySelectorAll<HTMLElement>('.operations-grid').forEach((grid) => {
    const panels = Array.from(grid.querySelectorAll<HTMLElement>(':scope > .operations-panel'));
    if (!panels.length) return;
    const anyVisible = panels.some(
      (panel) => !panel.classList.contains('mobile-operations-hidden') && !panel.classList.contains('mobile-operations-collapsed'),
    );
    grid.classList.toggle('mobile-operations-grid-empty', !anyVisible);
  });
}

function clearMobileClasses() {
  operationsPanels().forEach((panel) => {
    panel.classList.remove('mobile-operations-hidden', 'mobile-operations-collapsed', 'mobile-operations-active');
    delete panel.dataset.mobileOperationsTitle;
  });
  document.querySelectorAll<HTMLElement>('.operations-grid.mobile-operations-grid-empty').forEach((grid) => {
    grid.classList.remove('mobile-operations-grid-empty');
  });
  document.documentElement.classList.remove('mobile-operations-picker-active');
}

export default function MobileOperationsSectionMenu() {
  const [mobile, setMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches);
  const [available, setAvailable] = useState<string[]>([]);
  const [active, setActive] = useState(() => sessionStorage.getItem('a-plus-mobile-operations-section') || '');
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(MOBILE_QUERY);
    const onChange = () => setMobile(media.matches);
    media.addEventListener?.('change', onChange);
    return () => media.removeEventListener?.('change', onChange);
  }, []);

  useEffect(() => {
    let frame = 0;
    const organize = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (!mobile) {
          clearMobileClasses();
          setAvailable([]);
          return;
        }

        const { panels, managerPage } = findOperationsContext();
        if (!managerPage) {
          clearMobileClasses();
          setAvailable([]);
          return;
        }

        document.documentElement.classList.add('mobile-operations-picker-active');
        const byTitle = new Map<string, HTMLElement>();
        panels.forEach((panel) => {
          const title = panelTitle(panel);
          if (!title) return;
          panel.dataset.mobileOperationsTitle = title;
          if (!byTitle.has(title)) byTitle.set(title, panel);
        });

        // Some deployments/enhancers can add operational cards outside the
        // standard list. Hide requested mobile-only exclusions by their heading
        // as well, not only by a fragile component position.
        document.querySelectorAll<HTMLElement>('h2, h3').forEach((heading) => {
          const title = heading.textContent?.trim() || '';
          if (!HIDDEN_ON_MOBILE.has(title)) return;
          const container = heading.closest<HTMLElement>('.operations-panel, section');
          container?.classList.add('mobile-operations-hidden');
        });

        panels.forEach((panel) => {
          const title = panelTitle(panel);
          panel.classList.toggle('mobile-operations-hidden', HIDDEN_ON_MOBILE.has(title));
        });

        const nextAvailable = SECTION_ORDER.filter((title) => byTitle.has(title) && !HIDDEN_ON_MOBILE.has(title));
        setAvailable((current) => current.join('|') === nextAvailable.join('|') ? current : nextAvailable);

        let selected = active;
        if (!selected || !nextAvailable.includes(selected)) {
          selected = nextAvailable[0] || '';
          if (selected) setActive(selected);
        }

        panels.forEach((panel) => {
          const title = panelTitle(panel);
          if (HIDDEN_ON_MOBILE.has(title)) return;
          if (!nextAvailable.includes(title)) return;
          const isActive = title === selected;
          panel.classList.toggle('mobile-operations-active', isActive);
          panel.classList.toggle('mobile-operations-collapsed', !isActive);
        });
        updateGridVisibility();
      });
    };

    organize();
    const observer = new MutationObserver(organize);
    observer.observe(document.getElementById('root') || document.body, { childList: true, subtree: true });
    window.addEventListener('popstate', organize);
    window.addEventListener('hashchange', organize);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener('popstate', organize);
      window.removeEventListener('hashchange', organize);
      clearMobileClasses();
    };
  }, [mobile, active]);

  useEffect(() => {
    if (active) sessionStorage.setItem('a-plus-mobile-operations-section', active);
  }, [active]);

  const activeLabel = useMemo(() => SHORT_LABELS[active] || active || 'Bereiche', [active]);
  if (!mobile || !available.length) return null;

  const choose = (title: string) => {
    setActive(title);
    setOpen(false);
    requestAnimationFrame(() => {
      const panel = operationsPanels().find((item) => panelTitle(item) === title);
      panel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  return (
    <>
      <button
        type="button"
        className="mobile-operations-picker-button"
        aria-expanded={open}
        aria-label="Administrationsbereich auswählen"
        onClick={() => setOpen((value) => !value)}
      >
        <span aria-hidden="true">☰</span>
        <span>{activeLabel}</span>
      </button>

      {open && (
        <div className="mobile-operations-picker-layer" role="presentation" onClick={() => setOpen(false)}>
          <div className="mobile-operations-picker-sheet" role="dialog" aria-modal="true" aria-label="Administrationsbereiche" onClick={(event) => event.stopPropagation()}>
            <div className="mobile-operations-picker-head">
              <div><strong>Bereich auswählen</strong><small>Nur der gewählte Bereich wird angezeigt.</small></div>
              <button type="button" aria-label="Schließen" onClick={() => setOpen(false)}>×</button>
            </div>
            <div className="mobile-operations-picker-grid">
              {available.map((title) => (
                <button
                  type="button"
                  key={title}
                  className={title === active ? 'active' : ''}
                  onClick={() => choose(title)}
                >
                  <strong>{SHORT_LABELS[title] || title}</strong>
                  <small>{title}</small>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

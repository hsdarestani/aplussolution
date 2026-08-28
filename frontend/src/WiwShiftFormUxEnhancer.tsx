import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import './wiw-shift-form-ux.css';

function text(value: Element | null) {
  return String(value?.textContent || '').replace(/\s+/g, ' ').trim();
}

function findForm() {
  return document.querySelector<HTMLElement>('.wiw-shift-form-screen');
}

function closeForm() {
  const cancel = document.querySelector<HTMLButtonElement>('.wiw-shift-form-screen .wiw-form-topbar button:first-child');
  cancel?.click();
}

function openLocationAfterClientChoice() {
  window.setTimeout(() => {
    const form = findForm();
    if (!form) return;
    const locationRow = Array.from(form.querySelectorAll<HTMLButtonElement>('button.wiw-form-row')).find((row) => {
      const rowText = text(row);
      return rowText.includes('Jobstandort') || Boolean(row.querySelector('ion-icon[icon*="location"]'));
    });
    locationRow?.click();
  }, 90);
}

export default function WiwShiftFormUxEnhancer() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const sync = () => {
      const isOpen = Boolean(findForm());
      setOpen(isOpen);
      document.body.classList.toggle('wiw-shift-form-active', isOpen);
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      document.body.classList.remove('wiw-shift-form-active');
    };
  }, []);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const choiceButton = target?.closest<HTMLButtonElement>('.wiw-choice-sheet > div > button');
      if (!choiceButton) return;
      const sheet = choiceButton.closest('.wiw-choice-sheet');
      const title = text(sheet?.querySelector('header b') || null);
      if (title === 'Kunde') openLocationAfterClientChoice();
    };

    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      closeForm();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <button type="button" className="wiw-form-back-fallback" aria-label="Zurück zum Dienstplan" onClick={closeForm}>
      <span aria-hidden="true">‹</span>
      <b>Zurück</b>
    </button>,
    document.body,
  );
}

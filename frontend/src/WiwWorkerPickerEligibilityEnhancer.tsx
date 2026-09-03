import { useEffect } from 'react';
import { api } from './api';

type WorkerMeta = {
  id: string;
  active?: boolean;
  schedule_groups?: string[];
  user_detail?: { name?: string; email?: string };
  employee_number?: string;
};

const VALID_GROUPS = new Set(['service', 'front_office', 'housekeeping']);

function unpack(value: any): any[] {
  return value?.results || value || [];
}

function normalize(value: string) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '');
}

function text(value: Element | null) {
  return String(value?.textContent || '').replace(/\s+/g, ' ').trim();
}

function groupForPositionLabel(label: string): string | null {
  const key = normalize(label);
  if (key === 'housekeeping' || key === 'houskeeping') return 'housekeeping';
  if (key === 'frontoffice' || key === 'rezeption' || key === 'reception') return 'front_office';
  if (['servicekraft', 'serviceleitung', 'barsupport'].includes(key)) return 'service';
  return null;
}

function currentShiftGroup(): string | null {
  const form = document.querySelector('.wiw-shift-form-screen');
  if (!form) return null;
  const rows = Array.from(form.querySelectorAll<HTMLElement>('.wiw-form-row'));

  // The position row is authoritative. This prevents a hotel shift whose
  // schedule_groups contains several areas from showing workers for the wrong one.
  for (const row of rows) {
    const copy = row.querySelector<HTMLElement>('.wiw-form-row-copy > span');
    const group = groupForPositionLabel(text(copy));
    if (group) return group;
  }

  // Fallback for an incomplete/new form where the position has not been chosen yet.
  const rowTexts = rows.map((row) => normalize(text(row)));
  if (rowTexts.some((value) => value === 'housekeeping')) return 'housekeeping';
  if (rowTexts.some((value) => value === 'frontoffice')) return 'front_office';
  if (rowTexts.some((value) => value === 'service')) return 'service';
  return null;
}

function isWorkerSheet(sheet: HTMLElement) {
  const title = text(sheet.querySelector('header b'));
  return title === 'Mitarbeiter auswählen / ändern' || title === 'Geeignete Benutzer';
}

function isSingleWorkerSelection(sheet: HTMLElement) {
  const title = text(sheet.querySelector('header b'));
  if (title === 'Mitarbeiter auswählen / ändern') return true;
  const form = document.querySelector('.wiw-shift-form-screen');
  if (!form) return false;
  return Array.from(form.querySelectorAll<HTMLElement>('.wiw-form-row'))
    .some((row) => /^1\s+Schicht(?:karte)?\b/i.test(text(row)));
}

export default function WiwWorkerPickerEligibilityEnhancer() {
  useEffect(() => {
    let cancelled = false;
    const workerGroups = new Map<string, Set<string>>();

    const loadWorkers = async () => {
      try {
        const payload = await api('workers/?ordering=user__last_name');
        if (cancelled) return;
        unpack(payload).forEach((worker: WorkerMeta) => {
          if (worker.active === false || String(worker.user_detail?.email || '').endsWith('@sync.invalid')) return;
          const name = worker.user_detail?.name || worker.user_detail?.email || worker.employee_number || '';
          if (!name) return;
          const groups = new Set((Array.isArray(worker.schedule_groups) ? worker.schedule_groups : []).filter((group) => VALID_GROUPS.has(group)));
          workerGroups.set(normalize(name), groups);
        });
        applyEligibility();
      } catch (error) {
        console.warn('Worker Zeitplan metadata could not be loaded', error);
      }
    };

    const applyEligibility = () => {
      const targetGroup = currentShiftGroup();
      document.querySelectorAll<HTMLElement>('.wiw-choice-sheet').forEach((sheet) => {
        if (!isWorkerSheet(sheet)) return;
        const buttons = Array.from(sheet.querySelectorAll<HTMLButtonElement>(':scope > div > button'));
        buttons.forEach((button) => {
          const name = normalize(text(button));
          const groups = workerGroups.get(name);
          const isCurrentSelection = button.classList.contains('selected');
          const eligible = !targetGroup || Boolean(groups?.has(targetGroup));
          // Keep the current assignment visible so it can be explicitly removed,
          // but all replacement candidates must match the shift's Zeitplan.
          button.hidden = !(eligible || isCurrentSelection);
          button.setAttribute('aria-hidden', button.hidden ? 'true' : 'false');
        });
      });
    };

    const observer = new MutationObserver(() => applyEligibility());
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });

    const onClick = (event: MouseEvent) => {
      const button = (event.target as HTMLElement | null)?.closest<HTMLButtonElement>('.wiw-choice-sheet > div > button');
      if (!button) return;
      const sheet = button.closest<HTMLElement>('.wiw-choice-sheet');
      if (!sheet || !isWorkerSheet(sheet) || !isSingleWorkerSelection(sheet)) return;
      // Clicking an already selected worker means deselecting it; keep the sheet
      // open in that case. A new single selection should finish immediately.
      if (button.classList.contains('selected')) return;
      window.setTimeout(() => {
        const finish = sheet.querySelector<HTMLButtonElement>('header button');
        finish?.click();
      }, 30);
    };

    document.addEventListener('click', onClick, true);
    void loadWorkers();

    return () => {
      cancelled = true;
      observer.disconnect();
      document.removeEventListener('click', onClick, true);
    };
  }, []);

  return null;
}

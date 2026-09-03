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
  if (['servicekraft', 'serviceleitung', 'barsupport', 'service'].includes(key)) return 'service';
  return null;
}

function currentShiftGroup(): string | null {
  const form = document.querySelector('.wiw-shift-form-screen');
  if (!form) return null;

  const rows = Array.from(form.querySelectorAll<HTMLElement>('.wiw-form-row'));

  // The concrete Position is authoritative. A hotel can have both Front Office
  // and Housekeeping in its Zeitplan, but the worker picker must follow the
  // actual position of the shift being edited.
  for (const row of rows) {
    const copy = row.querySelector<HTMLElement>('.wiw-form-row-copy > span');
    const group = groupForPositionLabel(text(copy));
    if (group) return group;
  }

  return null;
}

function isWorkerSheet(sheet: HTMLElement) {
  const title = text(sheet.querySelector('header b'));
  return title === 'Mitarbeiter auswählen / ändern' || title === 'Geeignete Benutzer';
}

export default function WiwWorkerPickerEligibilityEnhancer() {
  useEffect(() => {
    let cancelled = false;
    let frame = 0;
    const workerGroups = new Map<string, Set<string>>();

    const applyEligibility = () => {
      frame = 0;
      if (cancelled || workerGroups.size === 0) return;

      const targetGroup = currentShiftGroup();
      document.querySelectorAll<HTMLElement>('.wiw-choice-sheet').forEach((sheet) => {
        if (!isWorkerSheet(sheet)) return;

        const buttons = Array.from(sheet.querySelectorAll<HTMLButtonElement>(':scope > div > button'));
        buttons.forEach((button) => {
          const key = normalize(text(button));
          const groups = workerGroups.get(key);
          const selected = button.classList.contains('selected');
          const eligible = !targetGroup || Boolean(groups?.has(targetGroup));

          // Keep only a currently assigned legacy mismatch visible so the admin
          // can remove/replace it. All other candidates must match the shift's
          // Zeitplan (e.g. Housekeeping must not show Service workers).
          const visible = eligible || selected;
          button.hidden = !visible;
          button.setAttribute('aria-hidden', visible ? 'false' : 'true');
          button.dataset.wiwEligibility = eligible ? 'eligible' : selected ? 'legacy-current' : 'hidden';
          if (selected && !eligible && targetGroup) {
            button.title = 'Aktuelle Zuordnung – Zeitplan passt nicht zu dieser Schicht.';
          } else {
            button.removeAttribute('title');
          }
        });
      });
    };

    const scheduleApply = () => {
      if (cancelled || frame) return;
      frame = window.requestAnimationFrame(applyEligibility);
    };

    const loadWorkers = async () => {
      try {
        const payload = await api('workers/?ordering=user__last_name');
        if (cancelled) return;

        unpack(payload).forEach((worker: WorkerMeta) => {
          if (worker.active === false || String(worker.user_detail?.email || '').endsWith('@sync.invalid')) return;
          const name = worker.user_detail?.name || worker.user_detail?.email || worker.employee_number || '';
          if (!name) return;
          const groups = new Set(
            (Array.isArray(worker.schedule_groups) ? worker.schedule_groups : [])
              .filter((group) => VALID_GROUPS.has(group)),
          );
          workerGroups.set(normalize(name), groups);
        });
        scheduleApply();
      } catch (error) {
        // Do not block the picker if metadata cannot be refreshed. The native
        // React sheet remains usable and a later open can retry on page reload.
        console.warn('Worker Zeitplan metadata could not be loaded', error);
      }
    };

    // Only observe structure changes. The previous implementation observed every
    // selected-class mutation while also mutating the same sheet and performing a
    // synthetic click. On slower phones that could race React reconciliation and
    // leave a sheet looking frozen until another tap. Structural observation is
    // sufficient because a fresh sheet is mounted whenever a picker opens.
    const observer = new MutationObserver(scheduleApply);
    observer.observe(document.body, { childList: true, subtree: true });

    void loadWorkers();

    return () => {
      cancelled = true;
      observer.disconnect();
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  return null;
}

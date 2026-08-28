export type MobileAppearance = 'light' | 'dark';

const STORAGE_KEY = 'aplus:mobile-appearance';

export function getMobileAppearance(): MobileAppearance {
  if (typeof window === 'undefined') return 'light';
  return window.localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light';
}

export function applyMobileAppearance(next: MobileAppearance) {
  if (typeof document !== 'undefined') document.documentElement.dataset.aplusAppearance = next;
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, next);
    window.dispatchEvent(new CustomEvent('aplus-appearance-change', { detail: next }));
  }
}

export function installMobileAppearance() {
  const current = getMobileAppearance();
  if (typeof document !== 'undefined') document.documentElement.dataset.aplusAppearance = current;
  return current;
}

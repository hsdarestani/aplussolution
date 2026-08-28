export type MobileAppearance = 'light';

const STORAGE_KEY = 'aplus:mobile-appearance';

export function getMobileAppearance(): MobileAppearance {
  return 'light';
}

export function applyMobileAppearance(_next: MobileAppearance = 'light') {
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.aplusAppearance = 'light';
    document.documentElement.style.colorScheme = 'light';
    document.documentElement.classList.remove('dark', 'ion-palette-dark');
  }
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(STORAGE_KEY);
    window.dispatchEvent(new CustomEvent('aplus-appearance-change', { detail: 'light' }));
  }
}

export function installMobileAppearance() {
  applyMobileAppearance('light');
  return 'light' as const;
}

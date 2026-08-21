export type FriendlyPickerKind = 'date' | 'time' | 'datetime-local' | 'month' | 'week';

export const FRIENDLY_PICKER_TYPES: FriendlyPickerKind[] = ['date', 'time', 'datetime-local', 'month', 'week'];

const pad = (value: number) => String(value).padStart(2, '0');

export function pickerKindFromType(type?: string | null): FriendlyPickerKind | undefined {
  const normalized = String(type || '').toLowerCase() as FriendlyPickerKind;
  return FRIENDLY_PICKER_TYPES.includes(normalized) ? normalized : undefined;
}

export function localDateValue(date = new Date()) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function localTimeValue(date = new Date()) {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function localDateTimeValue(date = new Date()) {
  return `${localDateValue(date)}T${localTimeValue(date)}`;
}

function isoWeekStart(raw: string) {
  const match = /^(\d{4})-W(\d{2})$/.exec(raw);
  if (!match) return '';
  const year = Number(match[1]);
  const week = Number(match[2]);
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const jan4Day = jan4.getUTCDay() || 7;
  const monday = new Date(Date.UTC(year, 0, 4 - jan4Day + 1 + (week - 1) * 7));
  return `${monday.getUTCFullYear()}-${pad(monday.getUTCMonth() + 1)}-${pad(monday.getUTCDate())}`;
}

function isoWeekFromDate(raw: string) {
  const datePart = raw.slice(0, 10);
  const [year, month, day] = datePart.split('-').map(Number);
  if (!year || !month || !day) return '';
  const date = new Date(Date.UTC(year, month - 1, day));
  const weekday = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - weekday);
  const weekYear = date.getUTCFullYear();
  const yearStart = new Date(Date.UTC(weekYear, 0, 1));
  const week = Math.ceil((((date.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return `${weekYear}-W${pad(week)}`;
}

export function toIonDatetimeValue(kind: FriendlyPickerKind, raw?: string, now = new Date()) {
  const value = String(raw || '');
  if (kind === 'date') return value.slice(0, 10) || localDateValue(now);
  if (kind === 'time') {
    const time = value.includes('T') ? value.split('T')[1]?.slice(0, 5) : value.slice(0, 5);
    return `${localDateValue(now)}T${time || localTimeValue(now)}:00`;
  }
  if (kind === 'datetime-local') return value.slice(0, 16) || localDateTimeValue(now);
  if (kind === 'month') return value ? `${value.slice(0, 7)}-01` : `${localDateValue(now).slice(0, 7)}-01`;
  if (kind === 'week') return isoWeekStart(value) || localDateValue(now);
  return value;
}

export function normalizePickerOutput(kind: FriendlyPickerKind, selected?: string | string[] | null) {
  const raw = Array.isArray(selected) ? String(selected[0] || '') : String(selected || '');
  if (!raw) return '';
  if (kind === 'date') return raw.slice(0, 10);
  if (kind === 'time') {
    const timePart = raw.includes('T') ? raw.split('T')[1] || '' : raw;
    return timePart.slice(0, 5);
  }
  if (kind === 'datetime-local') return raw.slice(0, 16);
  if (kind === 'month') return raw.slice(0, 7);
  if (kind === 'week') return isoWeekFromDate(raw);
  return raw;
}

export function quickPickerValue(kind: FriendlyPickerKind, offsetDays = 0, now = new Date()) {
  const date = new Date(now);
  date.setDate(date.getDate() + offsetDays);
  if (kind === 'date') return localDateValue(date);
  if (kind === 'time') return `${localDateValue(date)}T${localTimeValue(date)}:00`;
  if (kind === 'datetime-local') return localDateTimeValue(date);
  if (kind === 'month') return `${localDateValue(date).slice(0, 7)}-01`;
  if (kind === 'week') return localDateValue(date);
  return localDateTimeValue(date);
}

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { IonButton, IonDatetime, IonIcon, IonModal } from '@ionic/react';
import { calendarOutline, timeOutline } from 'ionicons/icons';
import {
  FriendlyPickerKind,
  normalizePickerOutput,
  pickerKindFromType,
  quickPickerValue,
  toIonDatetimeValue,
} from './friendlyDateTime';
import './friendly-date-time.css';

type PickerTarget = {
  element: HTMLElement;
  kind: FriendlyPickerKind;
  label: string;
  value: string;
  min?: string;
  max?: string;
  step?: string;
};

const friendlySelector = [
  'ion-input[type="date"]',
  'ion-input[type="time"]',
  'ion-input[type="datetime-local"]',
  'ion-input[type="month"]',
  'ion-input[type="week"]',
  'input[type="date"]',
  'input[type="time"]',
  'input[type="datetime-local"]',
  'input[type="month"]',
  'input[type="week"]',
  'ion-input[data-aplus-picker-kind]',
  'input[data-aplus-picker-kind]',
].join(',');

function isIonInput(element: HTMLElement) {
  return element.tagName.toLowerCase() === 'ion-input';
}

function currentValue(element: HTMLElement) {
  const stored = element.dataset.aplusPickerValue;
  if (stored !== undefined) return stored;
  if (isIonInput(element)) return String((element as any).value ?? element.getAttribute('value') ?? '');
  return element instanceof HTMLInputElement ? element.value : '';
}

function fieldLabel(element: HTMLElement, kind: FriendlyPickerKind) {
  const explicit = element.getAttribute('label') || element.getAttribute('aria-label') || element.getAttribute('placeholder');
  if (explicit) return explicit.replace(/\s*\*\s*$/, '');
  const wrapped = element.closest('label')?.querySelector('span')?.textContent?.trim();
  if (wrapped) return wrapped.replace(/\s*\*\s*$/, '');
  if (kind === 'time') return 'Uhrzeit';
  if (kind === 'datetime-local') return 'Datum & Uhrzeit';
  if (kind === 'month') return 'Monat';
  if (kind === 'week') return 'Woche';
  return 'Datum';
}

function enhanceNativeInput(input: HTMLInputElement, kind: FriendlyPickerKind) {
  if (!input.dataset.aplusPickerKind) input.dataset.aplusPickerKind = kind;
  input.readOnly = true;
  input.inputMode = 'none';
  input.autocomplete = 'off';
  input.setAttribute('aria-haspopup', 'dialog');
  input.classList.add('aplus-friendly-native-picker');
}

function enhanceIonInput(element: HTMLElement, kind: FriendlyPickerKind) {
  if (!element.dataset.aplusPickerKind) element.dataset.aplusPickerKind = kind;
  element.setAttribute('readonly', '');
  element.setAttribute('inputmode', 'none');
  element.setAttribute('aria-haspopup', 'dialog');
  try { (element as any).readonly = true; } catch { /* Ionic property is best effort. */ }
  element.classList.add('aplus-friendly-ion-picker');
  const applyShadowState = () => {
    const native = element.shadowRoot?.querySelector('input') as HTMLInputElement | null;
    if (!native) return;
    native.readOnly = true;
    native.inputMode = 'none';
    native.autocomplete = 'off';
  };
  applyShadowState();
  const ready = (element as any).componentOnReady?.();
  if (ready?.then) void ready.then(applyShadowState).catch(() => undefined);
}

function enhanceElement(element: HTMLElement) {
  const storedKind = pickerKindFromType(element.dataset.aplusPickerKind);
  const currentKind = pickerKindFromType(element.getAttribute('type'));
  const kind = storedKind || currentKind;
  if (!kind) return;
  if (kind === 'datetime-local' || kind === 'time') return;
  if (isIonInput(element)) enhanceIonInput(element, kind);
  else if (element instanceof HTMLInputElement) enhanceNativeInput(element, kind);
}

function enhanceAll(root: ParentNode = document) {
  root.querySelectorAll<HTMLElement>(friendlySelector).forEach(enhanceElement);
  if (root instanceof HTMLElement && (root.matches(friendlySelector) || root.dataset.aplusPickerKind)) enhanceElement(root);
}

function targetFromEvent(event: Event) {
  return event.composedPath().find((node) => node instanceof HTMLElement && pickerKindFromType(node.dataset?.aplusPickerKind)) as HTMLElement | undefined;
}

function setNativeReactValue(input: HTMLInputElement, next: string) {
  const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
  descriptor?.set?.call(input, next);
  input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
  input.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
}

function displayValue(element: HTMLElement, next: string) {
  if (element.dataset.aplusPickerDisplay !== 'de-date' || !next) return next;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(next);
  return match ? `${match[3]}.${match[2]}.${match[1]}` : next;
}

function emitValue(element: HTMLElement, next: string) {
  const visible = displayValue(element, next);
  if (element.hasAttribute('data-aplus-picker-value')) element.dataset.aplusPickerValue = next;
  if (isIonInput(element)) {
    (element as any).value = visible;
    element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: next }, bubbles: true, composed: true }));
    element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: next }, bubbles: true, composed: true }));
  } else if (element instanceof HTMLInputElement) {
    setNativeReactValue(element, visible);
  }
  window.requestAnimationFrame(() => enhanceAll());
}

function minuteValues(step?: string) {
  const seconds = Number(step || 0);
  if (!seconds || seconds < 60 || seconds % 60 !== 0) return undefined;
  const minutes = seconds / 60;
  if (minutes < 1 || minutes > 30 || 60 % minutes !== 0) return undefined;
  return Array.from({ length: 60 / minutes }, (_, index) => index * minutes).join(',');
}

const germanMonths = [
  'Januar',
  'Februar',
  'März',
  'April',
  'Mai',
  'Juni',
  'Juli',
  'August',
  'September',
  'Oktober',
  'November',
  'Dezember',
];

const pad2 = (value: number) => String(value).padStart(2, '0');

export default function FriendlyDateTimePicker() {
  const [target, setTarget] = useState<PickerTarget>();
  const [draft, setDraft] = useState('');
  const openingRef = useRef(false);

  useEffect(() => {
    enhanceAll();
    let frame = 0;
    const scheduleEnhance = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => enhanceAll());
    };
    const observer = new MutationObserver(scheduleEnhance);
    observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['type'] });

    const openFromElement = (element: HTMLElement) => {
      const kind = pickerKindFromType(element.dataset.aplusPickerKind);
      if (!kind || openingRef.current || element.hasAttribute('disabled') || (element as any).disabled) return;
      openingRef.current = true;
      window.setTimeout(() => { openingRef.current = false; }, 120);
      const next: PickerTarget = {
        element,
        kind,
        label: fieldLabel(element, kind),
        value: currentValue(element),
        min: element.getAttribute('min') || undefined,
        max: element.getAttribute('max') || undefined,
        step: element.getAttribute('step') || undefined,
      };
      setDraft(toIonDatetimeValue(kind, next.value));
      setTarget(next);
      (document.activeElement as HTMLElement | null)?.blur?.();
    };

    const onPointer = (event: Event) => {
      const element = targetFromEvent(event);
      if (!element) return;
      event.preventDefault();
      event.stopPropagation();
      openFromElement(element);
    };
    const onClick = (event: Event) => {
      const element = targetFromEvent(event);
      if (!element) return;
      event.preventDefault();
      event.stopPropagation();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const element = targetFromEvent(event);
      if (!element) return;
      event.preventDefault();
      event.stopPropagation();
      openFromElement(element);
    };

    document.addEventListener('pointerdown', onPointer, true);
    document.addEventListener('click', onClick, true);
    document.addEventListener('keydown', onKey, true);
    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(frame);
      document.removeEventListener('pointerdown', onPointer, true);
      document.removeEventListener('click', onClick, true);
      document.removeEventListener('keydown', onKey, true);
    };
  }, []);

  useEffect(() => {
    if (!target) return;
    setDraft(toIonDatetimeValue(target.kind, target.value));
  }, [target]);

  const presentation = useMemo(() => {
    if (!target) return 'date' as const;
    if (target.kind === 'time') return 'time' as const;
    if (target.kind === 'datetime-local') return 'date-time' as const;
    if (target.kind === 'month') return 'month-year' as const;
    return 'date' as const;
  }, [target]);

  const icon = target?.kind === 'time' ? timeOutline : calendarOutline;
  const minutes = target && (target.kind === 'time' || target.kind === 'datetime-local') ? minuteValues(target.step) : undefined;
  const directDateParts = useMemo(() => {
    const fallback = new Date();
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(draft || '');
    return {
      year: Number(match?.[1] || fallback.getFullYear()),
      month: Number(match?.[2] || fallback.getMonth() + 1),
      day: Number(match?.[3] || fallback.getDate()),
    };
  }, [draft]);
  const directYearOptions = useMemo(() => {
    if (!target || (target.kind !== 'date' && target.kind !== 'month')) return [];
    const minYear = Number((target.min || '1900').slice(0, 4)) || 1900;
    const maxYear = Number((target.max || '2100').slice(0, 4)) || 2100;
    const lower = Math.min(minYear, maxYear);
    const upper = Math.max(minYear, maxYear);
    return Array.from({ length: upper - lower + 1 }, (_, index) => upper - index);
  }, [target]);

  function close() {
    setTarget(undefined);
  }

  function apply() {
    if (!target) return;
    emitValue(target.element, normalizePickerOutput(target.kind, draft));
    close();
  }

  function clearValue() {
    if (!target) return;
    emitValue(target.element, '');
    close();
  }

  function setQuick(offset: number) {
    if (!target) return;
    setDraft(quickPickerValue(target.kind, offset));
  }

  function setCalendarMonthOrYear(part: 'month' | 'year', raw: string) {
    if (!target || (target.kind !== 'date' && target.kind !== 'month')) return;
    const year = part === 'year' ? Number(raw) : directDateParts.year;
    const month = part === 'month' ? Number(raw) : directDateParts.month;
    if (!year || !month) return;
    const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const day = target.kind === 'month' ? 1 : Math.min(Math.max(directDateParts.day || 1, 1), lastDay);
    setDraft(`${String(year).padStart(4, '0')}-${pad2(month)}-${pad2(day)}`);
  }

  return (
    <IonModal
      isOpen={!!target}
      onDidDismiss={close}
      className="friendly-picker-modal"
      initialBreakpoint={0.96}
      breakpoints={[0, 0.96, 1]}
      handleBehavior="cycle"
    >
      <div className="friendly-picker-sheet">
        <div className="friendly-picker-head">
          <div className="friendly-picker-title">
            <span><IonIcon icon={icon} /></span>
            <div><small>AUSWÄHLEN</small><h2>{target?.label || 'Datum & Uhrzeit'}</h2></div>
          </div>
          <IonButton fill="clear" size="small" onClick={close}>Abbrechen</IonButton>
        </div>

        {!!target && (
          <div className="friendly-picker-quick">
            {target.kind === 'time' ? (
              <IonButton size="small" fill="outline" onClick={() => setQuick(0)}>Jetzt</IonButton>
            ) : target.kind === 'month' ? (
              <IonButton size="small" fill="outline" onClick={() => setQuick(0)}>Dieser Monat</IonButton>
            ) : (
              <>
                <IonButton size="small" fill="outline" onClick={() => setQuick(0)}>{target.kind === 'datetime-local' ? 'Heute / jetzt' : 'Heute'}</IonButton>
                <IonButton size="small" fill="outline" onClick={() => setQuick(1)}>Morgen</IonButton>
              </>
            )}
          </div>
        )}

        {!!target && (target.kind === 'date' || target.kind === 'month') && (
          <div className="friendly-picker-jump" aria-label="Monat und Jahr direkt auswählen">
            <label>
              <span>Monat</span>
              <select
                aria-label="Monat direkt auswählen"
                value={directDateParts.month}
                onChange={(event) => setCalendarMonthOrYear('month', event.currentTarget.value)}
              >
                {germanMonths.map((month, index) => <option key={month} value={index + 1}>{month}</option>)}
              </select>
            </label>
            <label>
              <span>Jahr</span>
              <select
                aria-label="Jahr direkt auswählen"
                value={directDateParts.year}
                onChange={(event) => setCalendarMonthOrYear('year', event.currentTarget.value)}
              >
                {directYearOptions.map((year) => <option key={year} value={year}>{year}</option>)}
              </select>
            </label>
          </div>
        )}

        <div className="friendly-picker-calendar">
          {!!target && (
            <IonDatetime
              key={`${target.kind}-${target.label}`}
              locale="de-DE"
              firstDayOfWeek={1}
              hourCycle="h23"
              presentation={presentation}
              preferWheel={target.kind === 'time'}
              value={draft}
              min={target.min ? toIonDatetimeValue(target.kind, target.min) : target.kind === 'date' || target.kind === 'month' ? '1900-01-01' : target.kind === 'datetime-local' ? '1900-01-01T00:00' : undefined}
              max={target.max ? toIonDatetimeValue(target.kind, target.max) : target.kind === 'date' || target.kind === 'month' ? '2100-12-31' : target.kind === 'datetime-local' ? '2100-12-31T23:59' : undefined}
              minuteValues={minutes}
              onIonChange={(event) => { const next=String(Array.isArray(event.detail.value) ? event.detail.value[0] || '' : event.detail.value || ''); if(target.kind==='date'&&next){emitValue(target.element,normalizePickerOutput(target.kind,next));close();}else setDraft(next); }}
            />
          )}
        </div>

        <div className="friendly-picker-actions">
          {!!target?.value && <IonButton expand="block" fill="clear" color="medium" onClick={clearValue}>Wert löschen</IonButton>}
          <IonButton expand="block" size="large" disabled={!draft} onClick={apply}>Übernehmen</IonButton>
        </div>
      </div>
    </IonModal>
  );
}

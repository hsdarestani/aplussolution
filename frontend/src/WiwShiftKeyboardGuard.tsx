import { useEffect } from 'react';
import { Keyboard } from '@capacitor/keyboard';

const FORM_SELECTOR = '.wiw-shift-form-screen';
const SCROLL_SELECTOR = '.wiw-form-scroll';
const EDITABLE_SELECTOR = 'textarea, input:not([type="checkbox"]):not([type="radio"]), [contenteditable="true"]';
const KEYBOARD_THRESHOLD = 80;

function currentForm() {
  return document.querySelector<HTMLElement>(FORM_SELECTOR);
}

function currentScroll(form: HTMLElement | null) {
  return form?.querySelector<HTMLElement>(SCROLL_SELECTOR) || null;
}

function editableInsideForm(target: EventTarget | Element | null) {
  if (!(target instanceof HTMLElement)) return null;
  if (!target.matches(EDITABLE_SELECTOR)) return null;
  return target.closest(FORM_SELECTOR) ? target : null;
}

export default function WiwShiftKeyboardGuard() {
  useEffect(() => {
    const viewport = window.visualViewport;
    let form: HTMLElement | null = null;
    let baselineHeight = Math.max(window.innerHeight, viewport?.height || 0);
    let nativeKeyboardHeight = 0;
    let keyboardVisible = false;
    let disposed = false;
    let revealTimers: number[] = [];
    let showHandle: { remove: () => Promise<void> } | undefined;
    let hideHandle: { remove: () => Promise<void> } | undefined;

    const clearRevealTimers = () => {
      revealTimers.forEach((timer) => window.clearTimeout(timer));
      revealTimers = [];
    };

    const viewportMetrics = () => {
      const visualHeight = Math.max(1, viewport?.height || window.innerHeight);
      const offsetTop = Math.max(0, viewport?.offsetTop || 0);
      const nativeUsable = nativeKeyboardHeight > 0
        ? Math.max(240, baselineHeight - nativeKeyboardHeight)
        : visualHeight;
      const usableHeight = nativeKeyboardHeight > 0
        ? Math.min(visualHeight, nativeUsable)
        : visualHeight;
      const inferredKeyboard = Math.max(0, baselineHeight - visualHeight - offsetTop);
      return {
        height: Math.max(240, Math.round(usableHeight)),
        offsetTop: Math.round(offsetTop),
        keyboardInset: Math.max(Math.round(inferredKeyboard), Math.round(nativeKeyboardHeight)),
      };
    };

    const reveal = (target?: HTMLElement | null) => {
      const activeForm = currentForm();
      const scroll = currentScroll(activeForm);
      const element = target || editableInsideForm(document.activeElement);
      if (!activeForm || !scroll || !element || !activeForm.contains(element)) return;

      const metrics = viewportMetrics();
      const header = activeForm.querySelector<HTMLElement>('.wiw-form-topbar');
      const headerHeight = header?.getBoundingClientRect().height || 58;
      const rect = element.getBoundingClientRect();
      const visibleTop = metrics.offsetTop + headerHeight + 14;
      const visibleBottom = metrics.offsetTop + metrics.height - 22;

      let delta = 0;
      if (rect.bottom > visibleBottom) delta = rect.bottom - visibleBottom;
      else if (rect.top < visibleTop) delta = rect.top - visibleTop;

      if (Math.abs(delta) > 1) {
        scroll.scrollBy({ top: delta, behavior: 'smooth' });
      }
    };

    const scheduleReveal = (target?: HTMLElement | null) => {
      clearRevealTimers();
      [0, 70, 180, 340].forEach((delay) => {
        revealTimers.push(window.setTimeout(() => reveal(target), delay));
      });
    };

    const syncViewport = () => {
      const nextForm = currentForm();
      if (nextForm !== form) {
        form?.classList.remove('wiw-keyboard-guarded', 'wiw-keyboard-visible');
        form = nextForm;
        nativeKeyboardHeight = 0;
        keyboardVisible = false;
        if (form) {
          baselineHeight = Math.max(window.innerHeight, viewport?.height || 0);
          form.classList.add('wiw-keyboard-guarded');
        }
      }
      if (!form) return;

      const metrics = viewportMetrics();
      const inferredVisible = metrics.keyboardInset >= KEYBOARD_THRESHOLD;
      keyboardVisible = nativeKeyboardHeight >= KEYBOARD_THRESHOLD || inferredVisible;

      form.style.setProperty('--wiw-visible-viewport-height', `${metrics.height}px`);
      form.style.setProperty('--wiw-visible-viewport-top', `${metrics.offsetTop}px`);
      form.style.setProperty('--wiw-keyboard-inset', `${metrics.keyboardInset}px`);
      form.classList.toggle('wiw-keyboard-visible', keyboardVisible);

      if (keyboardVisible) scheduleReveal();
    };

    const onFocusIn = (event: FocusEvent) => {
      const target = editableInsideForm(event.target);
      if (!target) return;
      target.classList.add('wiw-keyboard-focus-target');
      syncViewport();
      scheduleReveal(target);
    };

    const onFocusOut = (event: FocusEvent) => {
      editableInsideForm(event.target)?.classList.remove('wiw-keyboard-focus-target');
    };

    const onViewportChange = () => {
      if (!currentForm()) return;
      syncViewport();
    };

    const onWindowResize = () => {
      if (!currentForm()) return;
      if (!keyboardVisible && nativeKeyboardHeight === 0) {
        baselineHeight = Math.max(window.innerHeight, viewport?.height || 0);
      }
      syncViewport();
    };

    const observer = new MutationObserver(syncViewport);
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('focusin', onFocusIn, true);
    document.addEventListener('focusout', onFocusOut, true);
    viewport?.addEventListener('resize', onViewportChange);
    viewport?.addEventListener('scroll', onViewportChange);
    window.addEventListener('resize', onWindowResize);

    void Keyboard.addListener('keyboardWillShow', (info) => {
      nativeKeyboardHeight = Math.max(0, Number(info.keyboardHeight || 0));
      if (!currentForm()) return;
      syncViewport();
      scheduleReveal();
    }).then((handle) => {
      if (disposed) void handle.remove();
      else showHandle = handle;
    }).catch(() => undefined);

    void Keyboard.addListener('keyboardWillHide', () => {
      nativeKeyboardHeight = 0;
      keyboardVisible = false;
      const activeForm = currentForm();
      activeForm?.classList.remove('wiw-keyboard-visible');
      window.setTimeout(() => {
        baselineHeight = Math.max(window.innerHeight, viewport?.height || 0);
        syncViewport();
      }, 80);
    }).then((handle) => {
      if (disposed) void handle.remove();
      else hideHandle = handle;
    }).catch(() => undefined);

    syncViewport();

    return () => {
      disposed = true;
      clearRevealTimers();
      observer.disconnect();
      document.removeEventListener('focusin', onFocusIn, true);
      document.removeEventListener('focusout', onFocusOut, true);
      viewport?.removeEventListener('resize', onViewportChange);
      viewport?.removeEventListener('scroll', onViewportChange);
      window.removeEventListener('resize', onWindowResize);
      form?.classList.remove('wiw-keyboard-guarded', 'wiw-keyboard-visible');
      void showHandle?.remove();
      void hideHandle?.remove();
    };
  }, []);

  return null;
}

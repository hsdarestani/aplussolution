const SIGNATURE_SELECTOR = 'ion-textarea[label*="Signatur"], ion-textarea[label*="Signature"], ion-textarea[data-signature-pad]';

function emitValue(input: any, value: string) {
  input.value = value;
  input.dispatchEvent(new CustomEvent('ionInput', {
    detail: { value },
    bubbles: true,
    composed: true,
  }));
}

function enhanceSignatureInput(input: HTMLElement) {
  if (input.dataset.signatureEnhanced === '1') return;
  input.dataset.signatureEnhanced = '1';

  const shell = document.createElement('div');
  shell.className = 'aplus-signature-pad';
  shell.style.cssText = [
    'grid-column:1/-1',
    'display:flex',
    'flex-direction:column',
    'gap:8px',
    'margin-top:2px',
  ].join(';');

  const head = document.createElement('div');
  head.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:12px';

  const label = document.createElement('div');
  label.textContent = 'Signatur – mit Finger oder Maus zeichnen';
  label.style.cssText = 'font:600 13px/1.35 system-ui,-apple-system,sans-serif;color:#334155';

  const clear = document.createElement('button');
  clear.type = 'button';
  clear.textContent = 'Löschen';
  clear.style.cssText = [
    'border:0',
    'background:transparent',
    'color:#2457e6',
    'font:600 13px system-ui,-apple-system,sans-serif',
    'padding:6px 4px',
    'cursor:pointer',
  ].join(';');

  head.append(label, clear);

  const canvas = document.createElement('canvas');
  canvas.setAttribute('aria-label', 'Unterschrift zeichnen');
  canvas.style.cssText = [
    'display:block',
    'width:100%',
    'height:150px',
    'background:#fff',
    'border:1px solid #cbd5e1',
    'border-radius:12px',
    'touch-action:none',
    'cursor:crosshair',
    'box-sizing:border-box',
  ].join(';');

  const hint = document.createElement('small');
  hint.textContent = 'Bitte innerhalb des Feldes unterschreiben. Die Linie wird bewusst fein gespeichert.';
  hint.style.cssText = 'font:400 11px/1.4 system-ui,-apple-system,sans-serif;color:#64748b';

  shell.append(head, canvas, hint);
  input.insertAdjacentElement('afterend', shell);
  input.style.display = 'none';

  const context = canvas.getContext('2d');
  if (!context) return;
  const ctx: CanvasRenderingContext2D = context;

  let drawing = false;
  let hasInk = false;
  let lastX = 0;
  let lastY = 0;

  function sizeCanvas(preserve = true) {
    const previous = preserve && hasInk ? canvas.toDataURL('image/png') : '';
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
    canvas.width = Math.max(1, Math.round(rect.width * ratio));
    canvas.height = Math.max(1, Math.round(rect.height * ratio));
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = '#111827';
    ctx.lineWidth = 1.45;
    if (previous) {
      const image = new Image();
      image.onload = () => ctx.drawImage(image, 0, 0, rect.width, rect.height);
      image.src = previous;
    }
  }

  function point(event: PointerEvent) {
    const rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function start(event: PointerEvent) {
    event.preventDefault();
    const p = point(event);
    drawing = true;
    lastX = p.x;
    lastY = p.y;
    canvas.setPointerCapture?.(event.pointerId);
    ctx.beginPath();
    ctx.moveTo(lastX, lastY);
    ctx.lineTo(lastX + 0.01, lastY + 0.01);
    ctx.stroke();
    hasInk = true;
  }

  function move(event: PointerEvent) {
    if (!drawing) return;
    event.preventDefault();
    const p = point(event);
    ctx.beginPath();
    ctx.moveTo(lastX, lastY);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    lastX = p.x;
    lastY = p.y;
    hasInk = true;
  }

  function finish(event: PointerEvent) {
    if (!drawing) return;
    event.preventDefault();
    drawing = false;
    try { canvas.releasePointerCapture?.(event.pointerId); } catch { /* no-op */ }
    if (hasInk) emitValue(input as any, canvas.toDataURL('image/png'));
  }

  canvas.addEventListener('pointerdown', start);
  canvas.addEventListener('pointermove', move);
  canvas.addEventListener('pointerup', finish);
  canvas.addEventListener('pointercancel', finish);
  canvas.addEventListener('pointerleave', (event) => {
    if (drawing && event.buttons === 0) finish(event);
  });

  clear.addEventListener('click', () => {
    drawing = false;
    hasInk = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    emitValue(input as any, '');
  });

  requestAnimationFrame(() => sizeCanvas(false));
  const resize = new ResizeObserver(() => sizeCanvas(true));
  resize.observe(canvas);
}

function scan() {
  document.querySelectorAll<HTMLElement>(SIGNATURE_SELECTOR).forEach(enhanceSignatureInput);
}

export function installSignaturePad() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  if ((window as any).__aplusSignaturePadInstalled) return;
  (window as any).__aplusSignaturePadInstalled = true;

  const start = () => {
    scan();
    const observer = new MutationObserver(() => scan());
    observer.observe(document.body, { childList: true, subtree: true });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
}

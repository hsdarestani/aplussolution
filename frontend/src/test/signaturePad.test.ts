import { beforeEach, describe, expect, it, vi } from 'vitest';

import { installSignaturePad } from '../signaturePad';

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

describe('signaturePad', () => {
  beforeEach(() => {
    document.body.innerHTML = '<ion-textarea label="Signatur (Name handschriftlich eingeben)"></ion-textarea>';
    delete (window as any).__aplusSignaturePadInstalled;
    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      setTransform: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      clearRect: vi.fn(),
      drawImage: vi.fn(),
      lineCap: 'round',
      lineJoin: 'round',
      strokeStyle: '#111827',
      lineWidth: 1.45,
    } as any);
    vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,signature');
  });

  it('replaces the text signature field with a pointer canvas and emits PNG data', () => {
    const input = document.querySelector('ion-textarea') as HTMLElement;
    let emitted = '';
    input.addEventListener('ionInput', (event: any) => { emitted = event.detail.value; });

    installSignaturePad();

    const canvas = document.querySelector('canvas[aria-label="Unterschrift zeichnen"]') as HTMLCanvasElement;
    expect(canvas).toBeTruthy();
    expect(input.style.display).toBe('none');

    const down = new Event('pointerdown', { bubbles: true }) as any;
    Object.assign(down, { clientX: 10, clientY: 10, pointerId: 1 });
    canvas.dispatchEvent(down);
    const up = new Event('pointerup', { bubbles: true }) as any;
    Object.assign(up, { clientX: 20, clientY: 20, pointerId: 1 });
    canvas.dispatchEvent(up);

    expect(emitted).toBe('data:image/png;base64,signature');
    expect((input as any).value).toBe('data:image/png;base64,signature');
  });
});
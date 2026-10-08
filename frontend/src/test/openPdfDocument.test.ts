import { beforeEach, expect, test, vi } from 'vitest';

const native = vi.hoisted(() => ({
  write: vi.fn(),
  open: vi.fn(),
  platform: vi.fn(() => true),
}));
vi.mock('@capacitor/core', () => ({ Capacitor: { isNativePlatform: native.platform } }));
vi.mock('@capacitor/filesystem', () => ({
  Directory: { Cache: 'CACHE' },
  Filesystem: { writeFile: native.write },
}));
vi.mock('@capacitor/file-viewer', () => ({
  FileViewer: { openDocumentFromLocalPath: native.open },
}));

import { openPdfDocument, pdfFilename } from '../openPdfDocument';

beforeEach(() => {
  vi.clearAllMocks();
  native.platform.mockReturnValue(true);
  native.write.mockResolvedValue({ uri: 'file:///cache/pdf-preview/report.pdf' });
  native.open.mockResolvedValue(undefined);
});

test('opens native fullscreen document from a cached binary PDF', async () => {
  const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' });
  expect(await openPdfDocument(blob, 'Einsatzplan.pdf')).toBe(true);
  expect(native.write).toHaveBeenCalledWith(expect.objectContaining({
    directory: 'CACHE', recursive: true, data: btoa('%PDF-1.4'),
  }));
  expect(native.open).toHaveBeenCalledWith({
    path: 'file:///cache/pdf-preview/report.pdf',
  });
});

test('uses web fallback when not running inside a native app', async () => {
  native.platform.mockReturnValue(false);
  expect(await openPdfDocument(new Blob(['%PDF']), 'report.pdf')).toBe(false);
  expect(native.write).not.toHaveBeenCalled();
  expect(native.open).not.toHaveBeenCalled();
});

test('does not present an invalid or empty PDF', async () => {
  await expect(openPdfDocument(new Blob([]), 'empty.pdf')).rejects.toThrow('leer');
  expect(native.open).not.toHaveBeenCalled();
});

test('sanitizes document names', () => {
  expect(pdfFilename('../bad name.PDF')).toBe('bad_name.pdf');
});

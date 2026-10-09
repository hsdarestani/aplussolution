import { beforeEach, expect, test, vi } from 'vitest';

const native = vi.hoisted(() => ({ write: vi.fn(), isNative: vi.fn(() => true) }));
vi.mock('@capacitor/core', () => ({ Capacitor: { isNativePlatform: native.isNative } }));
vi.mock('@capacitor/filesystem', () => ({
  Filesystem: { writeFile: native.write },
  Directory: { Documents: 'DOCUMENTS' },
}));

import { saveSchedulePdf, safePdfFilename } from '../saveSchedulePdf';

beforeEach(() => {
  vi.clearAllMocks();
  native.isNative.mockReturnValue(true);
  native.write.mockResolvedValue({ uri: 'file:///Documents/Downloads/Prüfung.pdf' });
});

test('a tap saves a PDF directly to the persistent visible Files/Downloads folder', async () => {
  await saveSchedulePdf(new Blob(['%PDF-1.4'], { type: 'application/pdf' }), 'Prüfung Oktober.pdf');
  expect(native.write).toHaveBeenCalledWith({
    path: 'Downloads/Prüfung Oktober.pdf',
    data: btoa('%PDF-1.4'),
    directory: 'DOCUMENTS',
    recursive: true,
  });
});

test('an unsuccessful filesystem write rejects the download', async () => {
  native.write.mockRejectedValueOnce(new Error('Speicher voll'));
  await expect(saveSchedulePdf(new Blob(['%PDF']), 'report.pdf')).rejects.toThrow('Speicher voll');
});

test('empty PDF is rejected without writing anything', async () => {
  await expect(saveSchedulePdf(new Blob([]), 'report.pdf')).rejects.toThrow('leer');
  expect(native.write).not.toHaveBeenCalled();
});

test('keeps umlauts and spaces but prevents folder traversal', () => {
  expect(safePdfFilename('Einsatz für Zürich.pdf')).toBe('Einsatz für Zürich.pdf');
  expect(safePdfFilename('../secret/report')).toBe('_secret_report.pdf');
});

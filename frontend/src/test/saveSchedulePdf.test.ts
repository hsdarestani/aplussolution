import { beforeEach, expect, test, vi } from 'vitest';

const native = vi.hoisted(() => ({ write: vi.fn(), open: vi.fn(), isNative: vi.fn(() => true), platform: vi.fn(() => 'ios') }));
vi.mock('@capacitor/core', () => ({ Capacitor: { isNativePlatform: native.isNative, getPlatform: native.platform } }));
vi.mock('@capacitor/filesystem', () => ({
  Filesystem: { writeFile: native.write },
  Directory: { Documents: 'DOCUMENTS' },
}));
vi.mock('@capacitor/file-viewer', () => ({ FileViewer: { openDocumentFromLocalPath: native.open } }));

import { saveSchedulePdf, safePdfFilename } from '../saveSchedulePdf';

beforeEach(() => {
  vi.clearAllMocks();
  native.isNative.mockReturnValue(true);
  native.platform.mockReturnValue('ios');
  native.write.mockResolvedValue({ uri: 'file:///Documents/Downloads/Prüfung.pdf' });
  native.open.mockResolvedValue(undefined);
});

test('a tap saves a PDF directly to the persistent visible Files/Downloads folder', async () => {
  await saveSchedulePdf(new Blob(['%PDF-1.4'], { type: 'application/pdf' }), 'Prüfung Oktober.pdf');
  expect(native.write).toHaveBeenCalledWith({
    path: 'Downloads/Prüfung Oktober.pdf',
    data: btoa('%PDF-1.4'),
    directory: 'DOCUMENTS',
    recursive: true,
  });
  expect(native.open).toHaveBeenCalledExactlyOnceWith({
    path: 'file:///Documents/Downloads/Prüfung.pdf',
  });
  expect(native.write.mock.invocationCallOrder[0]).toBeLessThan(native.open.mock.invocationCallOrder[0]);
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

test('reports an open error without losing the previously saved file', async () => {
  native.open.mockRejectedValueOnce(new Error('Native viewer unavailable'));
  await expect(saveSchedulePdf(new Blob(['%PDF']), 'report.pdf')).rejects.toThrow(
    'PDF wurde gespeichert, konnte aber nicht automatisch geöffnet werden.',
  );
  expect(native.write).toHaveBeenCalledTimes(1);
  expect(native.open).toHaveBeenCalledTimes(1);
});

test('Android still saves without launching an iOS-specific viewer', async () => {
  native.platform.mockReturnValue('android');
  await saveSchedulePdf(new Blob(['%PDF']), 'report.pdf');
  expect(native.write).toHaveBeenCalledTimes(1);
  expect(native.open).not.toHaveBeenCalled();
});

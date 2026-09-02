import { beforeEach, expect, test, vi } from 'vitest';
const native = vi.hoisted(() => ({ write: vi.fn(), share: vi.fn() }));
vi.mock('@capacitor/core', () => ({ Capacitor: { isNativePlatform: () => true } }));
vi.mock('@capacitor/filesystem', () => ({ Filesystem: { writeFile: native.write }, Directory: { Cache: 'CACHE' } }));
vi.mock('@capacitor/share', () => ({ Share: { share: native.share } }));
import { saveSchedulePdf } from '../saveSchedulePdf';

beforeEach(() => {
  vi.clearAllMocks();
  native.write.mockResolvedValue({ uri: 'file:///cache/dienstplan/report.pdf' });
  native.share.mockResolvedValue({});
});
test('native PDF is written as binary and shared using a device file URI', async () => {
  await saveSchedulePdf(new Blob(['%PDF-1.4'], { type: 'application/pdf' }), 'report.pdf');
  expect(native.write).toHaveBeenCalledWith({ path: 'dienstplan/report.pdf', data: btoa('%PDF-1.4'), directory: 'CACHE', recursive: true });
  expect(native.share).toHaveBeenCalledWith(expect.objectContaining({ files: ['file:///cache/dienstplan/report.pdf'] }));
});
test('a failed write is surfaced and never attempts sharing', async () => {
  native.write.mockRejectedValueOnce(new Error('Speicher voll'));
  await expect(saveSchedulePdf(new Blob(['%PDF']), 'report.pdf')).rejects.toThrow('Speicher voll');
  expect(native.share).not.toHaveBeenCalled();
});

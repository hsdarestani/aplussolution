import { Capacitor } from '@capacitor/core';
import { Filesystem, Directory } from '@capacitor/filesystem';

/** Preserve the document's original display name, including umlauts/spaces. */
export function safePdfFilename(filename: string) {
  const name = String(filename || 'Dienstplan.pdf')
    .replace(/[\\/:*?"<>|\x00-\x1f]/g, '_')
    .replace(/^\.+/, '')
    .trim()
    .slice(0, 160);
  const safe = name || 'Dienstplan.pdf';
  return /\.pdf$/i.test(safe) ? safe : safe + '.pdf';
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60000);
}

/**
 * Download PDF without Preview or Share.
 * On iOS the app's Documents/Downloads folder is exposed in the Files app:
 * "Auf meinem iPhone" > "A+ Solution" > "Downloads".
 * Directory.Cache would not survive cleanup or be visible in Files.
 */
export async function saveSchedulePdf(blob: Blob, filename: string, _title = 'Dienstplan'): Promise<void> {
  if (!blob.size) throw new Error('Die PDF Datei ist leer.');
  const name = safePdfFilename(filename);

  if (Capacitor.isNativePlatform()) {
    const data = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('PDF konnte nicht gelesen werden.'));
      reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
      reader.readAsDataURL(blob);
    });
    await Filesystem.writeFile({
      path: 'Downloads/' + name,
      directory: Directory.Documents,
      data,
      recursive: true,
    });
    return;
  }

  downloadBlob(blob, name);
}

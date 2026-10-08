import { Capacitor } from '@capacitor/core';
import { Directory, Filesystem } from '@capacitor/filesystem';
import { FileViewer } from '@capacitor/file-viewer';

export function pdfFilename(value: string) {
  const safe = String(value || 'Dienstplan.pdf')
    .replace(/[^a-zA-Z0-9._-]/g, '_')
    .replace(/^[._-]+/, '')
    .slice(-120);
  return (safe || 'Dienstplan.pdf').replace(/\.pdf$/i, '') + '.pdf';
}

async function pdfBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('PDF konnte nicht gelesen werden.'));
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
    reader.readAsDataURL(blob);
  });
}

/**
 * Open a real native, fullscreen document viewer instead of showing a PDF
 * iframe inside the Ionic app shell. iOS provides native pinch-to-zoom and
 * the app's bottom tabs/filters cannot overlap the presented document.
 *
 * Returns false on the web so callers can keep the web fallback.
 * This native plugin is bundled by the publisher build (cap sync).
 */
export async function openPdfDocument(blob: Blob, filename: string): Promise<boolean> {
  if (!Capacitor.isNativePlatform()) return false;
  if (!blob.size) throw new Error('Die PDF Datei ist leer.');

  const name = pdfFilename(filename);
  // A distinct cache path prevents the native document controller from
  // showing a stale copy when an updated schedule has the same file name.
  const unique = `${Date.now()}_${name}`;
  const file = await Filesystem.writeFile({
    path: `pdf-preview/${unique}`,
    directory: Directory.Cache,
    data: await pdfBase64(blob),
    recursive: true,
  });
  await FileViewer.openDocumentFromLocalPath({ path: file.uri });
  return true;
}

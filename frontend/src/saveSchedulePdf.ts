import { Capacitor } from '@capacitor/core';
import { Filesystem, Directory } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';

function safeFilename(filename: string) {
  return filename.replace(/[^a-zA-Z0-9._-]/g, '_');
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

export async function saveSchedulePdf(blob: Blob, filename: string) {
  const normalizedFilename = safeFilename(filename || 'Dienstplan.pdf');

  if (Capacitor.isNativePlatform()) {
    const data = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('PDF konnte nicht gelesen werden.'));
      reader.onload = () => resolve(String(reader.result).split(',')[1]);
      reader.readAsDataURL(blob);
    });
    const file = await Filesystem.writeFile({
      path: 'dienstplan/' + normalizedFilename,
      directory: Directory.Cache,
      data,
      recursive: true,
    });
    await Share.share({ title: 'Dienstplan', files: [file.uri], dialogTitle: 'PDF teilen' });
    return;
  }

  // Mobile browsers that support Web Share Level 2 should behave like the app:
  // opening the system share sheet immediately after PDF creation instead of
  // silently downloading the file. Keep download as a compatibility fallback.
  const shareFile = new File([blob], normalizedFilename, { type: blob.type || 'application/pdf' });
  const shareData: ShareData = { title: 'Dienstplan', files: [shareFile] };
  const canShareFiles = typeof navigator.share === 'function'
    && (typeof navigator.canShare !== 'function' || navigator.canShare(shareData));

  if (canShareFiles) {
    try {
      await navigator.share(shareData);
      return;
    } catch (error: any) {
      // Cancelling the native share sheet is a completed user action; do not
      // surprise the user with an automatic download afterwards.
      if (error?.name === 'AbortError') return;
      console.warn('PDF share sheet unavailable, falling back to download', error);
    }
  }

  downloadBlob(blob, normalizedFilename);
}

import { Capacitor } from '@capacitor/core';
import { Filesystem, Directory } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';

export async function saveSchedulePdf(blob: Blob, filename: string) {
  if (Capacitor.isNativePlatform()) {
    const data = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('PDF konnte nicht gelesen werden.'));
      reader.onload = () => resolve(String(reader.result).split(',')[1]);
      reader.readAsDataURL(blob);
    });
    const file = await Filesystem.writeFile({
      path: 'dienstplan/' + filename.replace(/[^a-zA-Z0-9._-]/g, '_'),
      directory: Directory.Cache, data, recursive: true,
    });
    await Share.share({ title: 'Dienstplan', files: [file.uri], dialogTitle: 'PDF speichern oder teilen' });
    return;
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60000);
}

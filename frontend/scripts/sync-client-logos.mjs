import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

// These exact PNG files are published by each customer's own website.
// Include them in the native Android/iOS bundle; never substitute generated marks.
const destination = fileURLToPath(new URL('../public/client-logos/', import.meta.url));
const originals = [
  ['marthas-finest.png', 'https://marthas-finest.de/wp-content/uploads/2022/09/Design-ohne-Titel-5-480x480.png'],
  ['stadthaus-am-markt.png', 'https://stadthaus-am-markt.de/img/logo.png'],
  ['hotel-spenerhaus.png', 'https://spenerhaus.de/wp-content/uploads/2026/02/Spener_Wortmarke_rgb-2.png'],
];

const pngSignature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const isPng = (buffer) => buffer.length >= 300 && buffer.subarray(0, 8).equals(pngSignature);

await mkdir(destination, { recursive: true });

await Promise.all(originals.map(async ([filename, url]) => {
  const file = join(destination, filename);
  const bundled = await readFile(file).catch(() => null);
  if (bundled && isPng(bundled)) return;
  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(9000),
      headers: { 'Accept': 'image/png,image/*;q=0.9', 'User-Agent': 'APlusSolution-ClientLogoBundle/1.0' },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const buffer = Buffer.from(await response.arrayBuffer());
    if (!isPng(buffer)) {
      throw new Error('Official resource did not return a valid PNG');
    }
    await writeFile(file, buffer);
    console.log(`Bundled official customer logo: ${filename} (${buffer.length} bytes)`);
  } catch (error) {
    // An outage on a customer's website must not block an app build.
    // ShiftClientLogo retries the official URL at runtime and retains an
    // accessible client name if both images are unavailable.
    console.warn(`Official customer logo unavailable for bundle: ${filename}: ${error}`);
  }
}));

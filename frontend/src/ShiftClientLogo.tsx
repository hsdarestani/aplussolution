import React from 'react';

/**
 * Official client assets are copied into the app during prepare:build so they
 * continue to work inside the Android/iOS WebView without network access.
 * When a local asset is unavailable (for example in an unbuilt dev checkout),
 * retry its original official source, then display a readable name.
 */
const BRANDS = {
  marthas: {
    name: "Martha's finest",
    local: '/client-logos/marthas-finest.png',
    original: 'https://marthas-finest.de/wp-content/uploads/2022/09/Design-ohne-Titel-5-480x480.png',
  },
  stadthaus: {
    name: 'Stadthaus am Markt',
    local: '/client-logos/stadthaus-am-markt.png',
    original: 'https://stadthaus-am-markt.de/img/logo.png',
  },
  spenerhaus: {
    name: 'Hotel Spenerhaus',
    local: '/client-logos/hotel-spenerhaus.png',
    original: 'https://spenerhaus.de/wp-content/uploads/2026/02/Spener_Wortmarke_rgb-2.png',
  },
} as const;

export type ShiftClientBrand = keyof typeof BRANDS;
export const normalizeClientIdentity = (value: unknown) =>
  String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');

export function resolveShiftClientBrand(shift: { client_name?: string; location_name?: string }): ShiftClientBrand | null {
  const name = normalizeClientIdentity(shift?.client_name);
  const location = normalizeClientIdentity(shift?.location_name);
  if (name.includes('martha') || name.includes('marthasfinest')) return 'marthas';
  if (name.includes('stadthausammarkt') || name.includes('stadthaus')) return 'stadthaus';
  if (name.includes('spenerhaus')) return 'spenerhaus';

  // The Evangelische Akademie shift group in WIW is serviced by Martha's finest.
  // Only apply the venue alias where no other recognised customer was supplied.
  if (!name && location.includes('evangelischeakademie')) return 'marthas';
  if (!name && location.includes('stadthausammarkt')) return 'stadthaus';
  if (!name && location.includes('spenerhaus')) return 'spenerhaus';
  return null;
}

export default function ShiftClientLogo({ shift }: { shift: { client_name?: string; location_name?: string } }) {
  const key = resolveShiftClientBrand(shift);
  const brand = key ? BRANDS[key] : null;
  const label = brand?.name || shift?.client_name || shift?.location_name || 'Kunde';
  return (
    <span
      className={`wiw-client-logo ${key ? `wiw-client-logo--${key}` : 'is-fallback'}`}
      title={label}
      data-testid="shift-client-logo"
    >
      {brand ? (
        <img
          key={key}
          src={brand.local}
          alt={brand.name}
          decoding="async"
          loading="lazy"
          onError={(event) => {
            const image = event.currentTarget;
            if (!image.dataset.triedOriginal) {
              image.dataset.triedOriginal = 'true';
              image.src = brand.original;
            } else {
              image.hidden = true;
              image.parentElement?.classList.add('is-fallback');
            }
          }}
        />
      ) : null}
      <span className="wiw-client-logo-fallback">{label}</span>
    </span>
  );
}

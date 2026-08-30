export type SchedulePalette = {
  hue: number;
  accent: string;
  openBackground: string;
  filledBackground: string;
  openText: string;
  filledText: string;
  openMuted: string;
  filledMuted: string;
  legendBackground: string;
  legendText: string;
};

export const normalizeScheduleLabel = (value?: string) =>
  String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/ß/g, 'ss')
    .replace(/[^a-z0-9]/g, '');

export const isHotelClientName = (name?: string) => {
  const key = normalizeScheduleLabel(name);
  return key.includes('spenerhaus') || key.includes('phillippjakobspenerhaus') || key.includes('philippjakobspenerhaus');
};

export const isHotelPositionName = (name?: string) => {
  const key = normalizeScheduleLabel(name);
  return key.includes('housekeeping') || key.includes('houskeeping') || key.includes('frontoffice');
};

function vividPalette(hue: number): SchedulePalette {
  return {
    hue,
    accent: `hsl(${hue} 76% 36%)`,
    openBackground: `linear-gradient(90deg,hsl(${hue} 78% 88%) 0%,hsl(${hue} 70% 95%) 48%,#fff 100%)`,
    filledBackground: `linear-gradient(90deg,hsl(${hue} 72% 28%) 0%,hsl(${hue} 68% 39%) 52%,hsl(${hue} 60% 82%) 100%)`,
    openText: `hsl(${hue} 48% 19%)`,
    filledText: '#ffffff',
    openMuted: `hsl(${hue} 24% 38%)`,
    filledMuted: 'rgba(255,255,255,.88)',
    legendBackground: `hsl(${hue} 70% 91%)`,
    legendText: `hsl(${hue} 62% 25%)`,
  };
}

const blackPalette: SchedulePalette = {
  hue: 0,
  accent: '#111111',
  openBackground: 'linear-gradient(90deg,#d9d9d9 0%,#f2f2f2 52%,#fff 100%)',
  filledBackground: 'linear-gradient(90deg,#050505 0%,#1b1b1b 55%,#606060 100%)',
  openText: '#151515',
  filledText: '#ffffff',
  openMuted: '#5c5c5c',
  filledMuted: '#ededed',
  legendBackground: '#1a1a1a',
  legendText: '#ffffff',
};

const fallbackHues = [8, 42, 88, 138, 184, 224, 270, 318];
function fallbackPalette(key: string): SchedulePalette {
  if (!key) return vividPalette(198);
  let hash = 0;
  for (let index = 0; index < key.length; index += 1) hash = ((hash * 31) + key.charCodeAt(index)) >>> 0;
  return vividPalette(fallbackHues[hash % fallbackHues.length]);
}

function customHuePalette(hue: number): SchedulePalette {
  const normalized = ((Math.round(hue) % 360) + 360) % 360;
  return vividPalette(normalized);
}

export function schedulePalette(clientName?: string, _positionName?: string, customHue?: number | null): SchedulePalette {
  if (customHue != null && Number.isFinite(Number(customHue))) return customHuePalette(Number(customHue));
  const client = normalizeScheduleLabel(clientName);

  // Requested operational order is intentionally also reflected in a highly
  // separated color sequence: orange, wine, royal blue, black, green, gold,
  // violet, teal, magenta.
  if (client.includes('martha')) return vividPalette(24);
  if (client.includes('stadthausammarkt') || client.includes('stadhaus')) return vividPalette(350);
  if (isHotelClientName(clientName)) return vividPalette(220);
  if (client.includes('hofelcatering') || client.includes('hofel') || client.includes('hoefel')) return blackPalette;
  if (client.includes('hirschgarten') || client.includes('restauranthirschgarten')) return vividPalette(132);
  if (client.includes('messefrankfurt') || client === 'messe') return vividPalette(46);
  if (client.includes('ommia') || client.includes('omnia')) return vividPalette(282);
  if (client.includes('citybeach')) return vividPalette(184);
  if (client.includes('hofgut')) return vividPalette(320);
  return fallbackPalette(client);
}

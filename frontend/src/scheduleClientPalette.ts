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

function hexToRgb(hex: string) {
  const value = hex.replace('#', '');
  const normalized = value.length === 3 ? value.split('').map((part) => `${part}${part}`).join('') : value;
  return {
    r: parseInt(normalized.slice(0, 2), 16),
    g: parseInt(normalized.slice(2, 4), 16),
    b: parseInt(normalized.slice(4, 6), 16),
  };
}

function mixWithWhite(hex: string, amount: number) {
  const { r, g, b } = hexToRgb(hex);
  const mix = (value: number) => Math.round(value + (255 - value) * amount);
  return `rgb(${mix(r)} ${mix(g)} ${mix(b)})`;
}

function relativeLuminance(hex: string) {
  const { r, g, b } = hexToRgb(hex);
  const channel = (value: number) => {
    const normalized = value / 255;
    return normalized <= 0.03928 ? normalized / 12.92 : Math.pow((normalized + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function exactPalette(hex: string): SchedulePalette {
  const accent = hex.toUpperCase();
  const darkText = relativeLuminance(accent) > 0.5 ? '#1b1b1b' : '#ffffff';
  return {
    hue: 0,
    accent,
    openBackground: `linear-gradient(90deg,${mixWithWhite(accent, 0.78)} 0%,${mixWithWhite(accent, 0.92)} 52%,#fff 100%)`,
    filledBackground: `linear-gradient(90deg,${accent} 0%,${accent} 58%,${mixWithWhite(accent, 0.42)} 100%)`,
    openText: '#182230',
    filledText: darkText,
    openMuted: '#667085',
    filledMuted: darkText === '#ffffff' ? 'rgba(255,255,255,.88)' : 'rgba(27,27,27,.76)',
    legendBackground: mixWithWhite(accent, 0.84),
    legendText: '#182230',
  };
}

const blackPalette: SchedulePalette = exactPalette('#000000');

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

export function schedulePalette(clientName?: string, positionName?: string, customHue?: number | null): SchedulePalette {
  const client = normalizeScheduleLabel(clientName);
  const position = normalizeScheduleLabel(positionName);

  // Fixed operational colors requested for the WIW schedule. These take
  // precedence over historic/manual shift hues so old cards immediately use
  // the same customer/department color as newly created shifts.
  if (isHotelClientName(clientName)) {
    if (position.includes('housekeeping') || position.includes('houskeeping')) return exactPalette('#58B2EE');
    if (position.includes('frontoffice') || position.includes('rezeption') || position.includes('reception')) return exactPalette('#030E6C');
    return exactPalette('#030E6C');
  }
  if (client.includes('stadthausammarkt') || client.includes('stadhaus')) return exactPalette('#AB5209');
  if (client.includes('martha')) return exactPalette('#FFBF00');
  if (client.includes('hirschgarten') || client.includes('restauranthirschgarten')) return exactPalette('#2C9B16');
  if (client.includes('citybeach')) return blackPalette;
  if (client.includes('manuelhofel') || client.includes('hofelcatering') || client.includes('hofel') || client.includes('hoefel')) return exactPalette('#515151');

  if (customHue != null && Number.isFinite(Number(customHue))) return customHuePalette(Number(customHue));
  if (client.includes('messefrankfurt') || client === 'messe') return vividPalette(46);
  if (client.includes('ommia') || client.includes('omnia')) return vividPalette(282);
  if (client.includes('hofgut')) return vividPalette(320);
  return fallbackPalette(client);
}

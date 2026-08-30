export type SchedulePalette = {
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

const defaultPalette: SchedulePalette = {
  accent: '#0b4d6b',
  openBackground: 'linear-gradient(90deg,#e7f2f7 0%,#f4f9fb 48%,#ffffff 100%)',
  filledBackground: 'linear-gradient(90deg,#0b4d6b 0%,#1c6684 42%,#e8f2f6 100%)',
  openText: '#20313a',
  filledText: '#ffffff',
  openMuted: '#667985',
  filledMuted: '#e8f3f8',
  legendBackground: '#eaf4f8',
  legendText: '#17465a',
};

function customHuePalette(hue: number): SchedulePalette {
  return {
    accent: `hsl(${hue} 68% 42%)`,
    openBackground: `linear-gradient(90deg,hsl(${hue} 72% 91%) 0%,hsl(${hue} 60% 97%) 52%,#fff 100%)`,
    filledBackground: `linear-gradient(90deg,hsl(${hue} 63% 37%) 0%,hsl(${hue} 58% 48%) 48%,hsl(${hue} 55% 91%) 100%)`,
    openText: '#263238',
    filledText: '#ffffff',
    openMuted: '#667085',
    filledMuted: '#f4f7fb',
    legendBackground: `hsl(${hue} 72% 94%)`,
    legendText: `hsl(${hue} 55% 29%)`,
  };
}

export function schedulePalette(clientName?: string, positionName?: string, customHue?: number | null): SchedulePalette {
  if (customHue != null && Number.isFinite(Number(customHue))) return customHuePalette(Number(customHue));
  const client = normalizeScheduleLabel(clientName);
  const position = normalizeScheduleLabel(positionName);

  if (client.includes('martha')) return {
    accent: '#d97706',
    openBackground: 'linear-gradient(90deg,#ffedd5 0%,#fff7ed 55%,#ffffff 100%)',
    filledBackground: 'linear-gradient(90deg,#c86404 0%,#e98216 48%,#ffe5bd 100%)',
    openText: '#5a3412', filledText: '#ffffff', openMuted: '#8a6747', filledMuted: '#fff3e2', legendBackground: '#fff0db', legendText: '#8a4708',
  };
  if (client.includes('messefrankfurt') || client === 'messe' || client.includes('ommia') || client.includes('omnia') || client.includes('hofgut')) return {
    accent: '#b8bec7',
    openBackground: 'linear-gradient(90deg,#ffffff 0%,#ffffff 72%,#f8fafc 100%)',
    filledBackground: 'linear-gradient(90deg,#d5dae1 0%,#f0f2f5 35%,#ffffff 100%)',
    openText: '#374151', filledText: '#202733', openMuted: '#7b8490', filledMuted: '#596270', legendBackground: '#ffffff', legendText: '#4b5563',
  };
  if (client.includes('stadthausammarkt') || client.includes('stadhaus')) return {
    accent: '#815b3a',
    openBackground: 'linear-gradient(90deg,#efe6dd 0%,#f8f3ee 58%,#ffffff 100%)',
    filledBackground: 'linear-gradient(90deg,#725035 0%,#986c49 48%,#e8d7c8 100%)',
    openText: '#493425', filledText: '#ffffff', openMuted: '#7c6859', filledMuted: '#f7eee7', legendBackground: '#eee4db', legendText: '#60442f',
  };
  if (client.includes('citybeach')) return {
    accent: '#168ca5',
    openBackground: 'linear-gradient(90deg,#dff4f8 0%,#eefafd 58%,#ffffff 100%)',
    filledBackground: 'linear-gradient(90deg,#0f778d 0%,#159ab4 48%,#cceff5 100%)',
    openText: '#164b57', filledText: '#ffffff', openMuted: '#56808a', filledMuted: '#ecfbfe', legendBackground: '#ddf4f8', legendText: '#126579',
  };
  if (client.includes('hirschgarten') || client.includes('restauranthirschgarten')) return {
    accent: '#3f7d44',
    openBackground: 'linear-gradient(90deg,#e3f0e3 0%,#f2f8f2 58%,#ffffff 100%)',
    filledBackground: 'linear-gradient(90deg,#356b3a 0%,#4b8a50 48%,#d7ead8 100%)',
    openText: '#27472b', filledText: '#ffffff', openMuted: '#617963', filledMuted: '#eef8ef', legendBackground: '#e3f0e3', legendText: '#315f35',
  };
  if (isHotelClientName(clientName)) {
    if (position.includes('frontoffice')) return {
      accent: '#647d92',
      openBackground: 'linear-gradient(90deg,#eceff1 0%,#eceff1 52%,#dceaf5 100%)',
      filledBackground: 'linear-gradient(90deg,#737980 0%,#737980 52%,#4d789c 100%)',
      openText: '#38434c', filledText: '#ffffff', openMuted: '#6b747d', filledMuted: '#eef6fc', legendBackground: '#edf1f4', legendText: '#4d6070',
    };
    if (position.includes('housekeeping') || position.includes('houskeeping')) return {
      accent: '#766889',
      openBackground: 'linear-gradient(90deg,#eceff1 0%,#eceff1 52%,#e9e1f0 100%)',
      filledBackground: 'linear-gradient(90deg,#737980 0%,#737980 52%,#725d86 100%)',
      openText: '#3e4147', filledText: '#ffffff', openMuted: '#72747b', filledMuted: '#f6effa', legendBackground: '#efedf2', legendText: '#60566d',
    };
    return {
      accent: '#72777d',
      openBackground: 'linear-gradient(90deg,#eceff1 0%,#f5f6f7 58%,#ffffff 100%)',
      filledBackground: 'linear-gradient(90deg,#747980 0%,#92979d 52%,#dfe2e5 100%)',
      openText: '#3f4449', filledText: '#ffffff', openMuted: '#747a80', filledMuted: '#f7f8f9', legendBackground: '#eceff1', legendText: '#565d63',
    };
  }
  if (client.includes('hofelcatering') || client.includes('hofel') || client.includes('hoefel')) return {
    accent: '#111827',
    openBackground: 'linear-gradient(90deg,#e5e7eb 0%,#f5f6f8 58%,#ffffff 100%)',
    filledBackground: 'linear-gradient(90deg,#0b0f17 0%,#111827 58%,#333b48 100%)',
    openText: '#1f2937', filledText: '#ffffff', openMuted: '#6b7280', filledMuted: '#e5e7eb', legendBackground: '#111827', legendText: '#ffffff',
  };
  return defaultPalette;
}

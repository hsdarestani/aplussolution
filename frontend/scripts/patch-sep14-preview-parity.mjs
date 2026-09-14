import { readFileSync, writeFileSync } from 'node:fs';

const path = new URL('../src/WiwScheduleMobile.tsx', import.meta.url);
const source = readFileSync(path, 'utf8');
if (source.includes('SEP14_PREVIEW_PARITY')) process.exit(0);

let next = source;

function replaceRequired(needle, replacement, label) {
  if (!next.includes(needle)) throw new Error(`SEP14 preview parity marker changed: ${label}`);
  next = next.replace(needle, replacement);
}

replaceRequired(
  'function AdjacentWeekPreview({ weekStart, groupFilter, query }: { weekStart: string; groupFilter: string[]; query: string }) {',
  `function previewShiftCardStyle(shift: any) {
  const palette = schedulePalette(shift?.client_name, shift?.position_name, shift?.color_hue);
  return {
    '--wiw-client-hue': String(palette.hue),
    '--wiw-card-accent': palette.accent,
    '--wiw-card-open-bg': palette.openBackground,
    '--wiw-card-filled-bg': palette.filledBackground,
    '--wiw-card-open-text': palette.openText,
    '--wiw-card-filled-text': palette.filledText,
    '--wiw-card-open-muted': palette.openMuted,
    '--wiw-card-filled-muted': palette.filledMuted,
  } as React.CSSProperties;
}

function AdjacentWeekPreview({ weekStart, groupFilter, query }: { weekStart: string; groupFilter: string[]; query: string }) {`,
  'preview card palette helper',
);

next = next.replaceAll(
  'className="wiw-adjacent-day-section"',
  'className="wiw-adjacent-day-section wiw-day-visual"',
);
next = next.replaceAll(
  'className="wiw-day-section"',
  'className="wiw-day-section wiw-day-visual"',
);

replaceRequired(
  `{cards.map((card: CardRow) => <div className={\`wiw-shift-card \${card.isOpen ? 'is-open' : 'is-filled'}\`} key={card.key}>\n          <div className="wiw-card-line primary"><span className="wiw-card-person"><WorkerAvatar worker={card.worker} /><b>{shortWorkerName(card.worker?.name) || 'OpenShift'}</b></span><span>{formatTimeIso(card.shift.starts_at)}–{formatTimeIso(card.shift.ends_at)}</span></div>\n          <div className="wiw-card-line secondary"><span>{positionShortLabel(card.shift.position_name)}</span><small>{card.shift.location_name || 'Einsatzort'}</small></div>\n        </div>)}`,
  `{cards.map((card: CardRow, index: number) => <React.Fragment key={card.key}>{index > 0 && clientKey(cards[index - 1].shift) !== clientKey(card.shift) ? <div className="wiw-client-divider" aria-hidden="true" /> : null}<button type="button" tabIndex={-1} className={\`wiw-shift-card \${card.shift.status === 'draft' ? 'is-draft' : card.isOpen ? 'is-open' : 'is-filled'}\`} style={previewShiftCardStyle(card.shift)}>\n          <div className="wiw-card-line primary"><span className="wiw-card-person"><WorkerAvatar worker={card.worker} /><b>{shortWorkerName(card.worker?.name) || (card.shift.status === 'draft' ? 'Entwurf' : 'OpenShift')}{card.isOpen && card.shift.status !== 'draft' ? <span className="wiw-open-alert">!</span> : null}</b></span><span>{formatTimeIso(card.shift.starts_at)}–{formatTimeIso(card.shift.ends_at)}</span></div>\n          <div className="wiw-card-line secondary"><span className={card.isOpen ? 'open' : ''}>{positionShortLabel(card.shift.position_name)}</span><small>{card.shift.location_name || 'Einsatzort'}</small></div>\n        </button></React.Fragment>)}`,
  'preview card markup parity',
);

writeFileSync(path, `// SEP14_PREVIEW_PARITY\n${next}`);

import { readFileSync, writeFileSync } from 'node:fs';

const path = new URL('../src/WiwScheduleMobile.tsx', import.meta.url);
const source = readFileSync(path, 'utf8');
if (source.includes('SEP13_E2E_FOLLOWUP')) process.exit(0);

let next = source;
const selectedWorkerMarker = `  const selectedWorkerNames = form.workers.map((workerId) => workerChoices.find((choice) => choice.value === workerId)?.label).filter(Boolean).join(', ');`;
if (!next.includes(selectedWorkerMarker)) throw new Error('SEP13 follow-up marker changed: selectedWorkerNames');
const pdfWorkerChoices = `  const pdfWorkerChoices = useMemo<Choice[]>(() => workers
    .map((item: any) => ({ value: String(item.id), label: item.user_detail?.name || item.user_detail?.email || item.employee_number || 'Mitarbeiter' }))
    .sort((a: Choice, b: Choice) => a.label.localeCompare(b.label, 'de', { sensitivity: 'base' })), [workers]);\n`;
next = next.replace(selectedWorkerMarker, `${pdfWorkerChoices}${selectedWorkerMarker}`);

const pdfWorkersMarker = `{workerChoices.map((choice) => <button type="button" key={choice.value} className={pdf.workers.includes(choice.value) ? 'active' : ''}`;
if (!next.includes(pdfWorkersMarker)) throw new Error('SEP13 follow-up marker changed: PDF worker choices');
next = next.replace(pdfWorkersMarker, `{pdfWorkerChoices.map((choice) => <button type="button" key={choice.value} className={pdf.workers.includes(choice.value) ? 'active' : ''}`);

writeFileSync(path, `// SEP13_E2E_FOLLOWUP\n${next}`);

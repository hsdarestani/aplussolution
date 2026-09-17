import fs from 'node:fs';

const file = new URL('../src/WiwScheduleMobile.tsx', import.meta.url);
let source = fs.readFileSync(file, 'utf8');

const oldBlock = `    setForm((current) => ({
      ...current,
      required_count: 1,
      publish_now: true,
      workers: [],
      apply_all: false,
    }));`;

const newBlock = `    setForm((current) => ({
      ...current,
      required_count: 1,
      publish_now: true,
      // Keep the original direct assignment when copying an assigned shift.
      // The normal save flow creates the copy as draft, then calls /assign/;
      // that produces the employee assignment notification/push for the new date.
      // OpenShifts still have an empty workers array, so they remain OpenShifts.
      workers: current.workers,
      apply_all: false,
    }));`;

if (source.includes(oldBlock)) {
  source = source.replace(oldBlock, newBlock);
  fs.writeFileSync(file, source);
  console.log('Applied copied-shift assignment/push patch.');
} else if (source.includes('workers: current.workers,') && source.includes('Keep the original direct assignment when copying')) {
  console.log('Copied-shift assignment/push patch already applied.');
} else {
  throw new Error('Copy-shift patch marker changed: prepareCopyAsOpenShift');
}

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ native: false, apiBlob: vi.fn(), save: vi.fn() }));
vi.mock('@capacitor/core', () => ({ Capacitor: { isNativePlatform: () => mocks.native } }));
vi.mock('../api', () => ({ apiBlob: mocks.apiBlob }));
vi.mock('../saveSchedulePdf', () => ({ saveSchedulePdf: mocks.save }));
import WeeklyStundenzettel, { previousBerlinWeek } from '../WeeklyStundenzettel';
beforeEach(() => { mocks.native = false; mocks.apiBlob.mockReset(); mocks.save.mockReset(); });
test('previous full week uses Berlin and ISO week year at new year', () => {
  expect(previousBerlinWeek(new Date('2026-11-15T20:00:00Z'))).toBe('2026-W45');
  expect(previousBerlinWeek(new Date('2021-01-04T09:00:00Z'))).toBe('2020-W53');
  expect(previousBerlinWeek(new Date('2026-11-15T23:30:00Z'))).toBe('2026-W46');
});
test('native applications have no export control', () => {
  mocks.native = true; const { container } = render(<WeeklyStundenzettel />);
  expect(container).toBeEmptyDOMElement();
});
test('chosen week and department download PDF and expose failures', async () => {
  const blob = new Blob(['pdf']);
  mocks.apiBlob.mockResolvedValueOnce({ blob, filename: 'Stundenzettel - HK - KW44.pdf' });
  render(<WeeklyStundenzettel />);
  fireEvent.change(screen.getByLabelText('Kalenderwoche'), { target: { value: '2026-W44' } });
  fireEvent.click(screen.getByRole('button', { name: 'Housekeeping · PDF' }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledWith(blob, 'Stundenzettel - HK - KW44.pdf'));
  expect(mocks.apiBlob).toHaveBeenCalledWith('reports/stundenzettel.pdf?week=2026-W44&group=housekeeping');
  await screen.findByText('PDF wurde heruntergeladen.');
  mocks.apiBlob.mockRejectedValueOnce(new Error('Keine Arbeitszeiten vorhanden.'));
  fireEvent.click(screen.getByRole('button', { name: 'Front Office · PDF' }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Keine Arbeitszeiten vorhanden.'));
});

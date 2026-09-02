import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../api', () => ({ api: apiMock }));
vi.mock('@ionic/react', () => ({
  IonButton: ({ children, onClick, disabled }: any) => <button disabled={disabled} onClick={onClick}>{children}</button>,
  IonSpinner: () => <span>Loading</span>,
  IonToggle: () => <span />,
}));
import NotificationPushSettings from '../NotificationPushSettings';
test('actual text is editable but saving unchanged does not freeze the dynamic template', async () => {
  const rule = { key: 'open_shift', label: 'Neue OpenShifts', enabled: true, title_template: '{title}', body_template: '{body}', display_title: 'Neue Schicht verfügbar', display_body: '04.09.2026 · Frankfurt', preview_source: 'latest' };
  apiMock.mockResolvedValue({ rules: [rule] });
  render(<NotificationPushSettings role="admin" />);
  expect(await screen.findByDisplayValue('Neue Schicht verfügbar')).toBeTruthy();
  fireEvent.click(screen.getByText('Speichern'));
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith('push/settings/', expect.objectContaining({ method: 'PUT' })));
  expect(JSON.parse(apiMock.mock.calls.find(call => call[1]?.method === 'PUT')![1].body).rules[0].body_template).toBe('{body}');
  await waitFor(() => expect(screen.getByText('Speichern')).not.toBeDisabled());
  fireEvent.change(screen.getByDisplayValue('Neue Schicht verfügbar'), { target: { value: 'Neuer Einsatz' } });
  fireEvent.click(screen.getByText('Speichern'));
  await waitFor(() => expect(JSON.parse(apiMock.mock.calls.filter(call => call[1]?.method === 'PUT').slice(-1)[0]![1].body).rules[0].title_template).toBe('Neuer Einsatz'));
});

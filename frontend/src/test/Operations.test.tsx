import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ionic/react', () => {
  const component = (tag = 'div') => ({ children, ...props }: any) => React.createElement(tag, props, children);
  return {
    IonBadge: component('span'), IonButton: component('button'), IonCard: component(), IonCardContent: component(),
    IonIcon: component('i'), IonInput: component('input'), IonItem: component(), IonLabel: component('label'),
    IonModal: ({ isOpen, children }: any) => isOpen ? <div>{children}</div> : null,
    IonSelect: component('select'), IonSelectOption: component('option'), IonSpinner: component(),
    IonTextarea: component('textarea'), IonToast: component(), IonToggle: component('input'),
  };
});
vi.mock('ionicons/icons', () => ({ alertCircleOutline: 'icon', calendarOutline: 'icon', checkmarkCircleOutline: 'icon', cloudDownloadOutline: 'icon', copyOutline: 'icon', documentTextOutline: 'icon', notificationsOutline: 'icon', peopleOutline: 'icon', refreshOutline: 'icon', swapHorizontalOutline: 'icon', trashOutline: 'icon', warningOutline: 'icon' }));

const apiMock = vi.fn();
vi.mock('../api', () => ({ api: (...args: any[]) => apiMock(...args) }));
import Operations from '../Operations';

const admin = { id: '1', email: 'a', name: 'Admin', first_name: 'A', last_name: '', role: 'admin', phone: '' } as any;

function resultFor(path: string) {
  if (path === 'operations/') return { notifications: [], readiness: {}, conflicts: [], unavailable_assignments: [], coverage_gaps: [], overtime_risks: [] };
  if (path === 'operations/folders/') return { workers: [], clients: [] };
  if (path.startsWith('shifts/')) return [];
  if (path === 'integrations/wiw/status/') return { configured: true, latest_sync: { status: 'success', finished_at: '2026-07-26T08:00:00Z' } };
  if (path === 'document-catalog/') return { complete: false, documents: Array.from({ length: 8 }, (_, index) => ({ slug: `d${index}`, name: `Dokument ${index + 1}`, version: '1.0', source_format: 'docx', source_installed: index < 6, signature_roles: ['employee'] })) };
  if (path === 'automation/orders/packages/') return { results: [] };
  if (path === 'working-time/settings/') return { employees: [] };
  if (path === 'working-time/records/') return { results: [] };
  return {};
}

describe('Operations integrations', () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path: string) => Promise.resolve(resultFor(path)));
  });

  it('loads and displays WIW readiness and all eight documents', async () => {
    render(<Operations user={admin} />);
    await waitFor(() => expect(screen.getByTestId('wiw-integration-panel')).toBeInTheDocument());
    expect(screen.getByText('Verbunden')).toBeInTheDocument();
    expect(screen.getByText('6/8 installiert')).toBeInTheDocument();
    expect(screen.getByText('Dokument 8')).toBeInTheDocument();
    expect(screen.getByTestId('order-automation-panel')).toBeInTheDocument();
    expect(screen.getByTestId('working-time-panel')).toBeInTheDocument();
    expect(apiMock).toHaveBeenCalledWith('integrations/wiw/status/');
    expect(apiMock).toHaveBeenCalledWith('document-catalog/');
  });

  it('does not show admin integration panels to a worker', async () => {
    const worker = { ...admin, role: 'worker' };
    apiMock.mockImplementation((path: string) => Promise.resolve(path === 'operations/' ? { notifications: [], availabilities: [], swaps: [], upcoming_shifts: [] } : { workers: [], clients: [] }));
    render(<Operations user={worker as any} />);
    await waitFor(() => expect(screen.getByText('Verfügbarkeit & Tausch')).toBeInTheDocument());
    expect(screen.queryByTestId('wiw-integration-panel')).not.toBeInTheDocument();
  });
});

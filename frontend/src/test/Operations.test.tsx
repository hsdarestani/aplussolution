import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Operations from '../Operations';
import { api } from '../api';

vi.mock('../api', () => ({ api: vi.fn() }));
vi.mock('@ionic/react', () => ({
  IonBadge: ({ children }: any) => <span>{children}</span>,
  IonButton: ({ children, ...props }: any) => <button {...props}>{children}</button>,
  IonIcon: (props: any) => <i {...props} />,
  IonInput: (props: any) => <input {...props} />,
  IonModal: ({ children }: any) => <div>{children}</div>,
  IonSelect: ({ children, ...props }: any) => <select {...props}>{children}</select>,
  IonSelectOption: ({ children, ...props }: any) => <option {...props}>{children}</option>,
  IonTextarea: (props: any) => <textarea {...props} />,
  IonToast: (props: any) => <div {...props} />,
  IonToggle: (props: any) => <input type="checkbox" {...props} />,
}));
vi.mock('ionicons/icons', () => ({ refreshOutline: 'icon', trashOutline: 'icon' }));

const apiMock = vi.mocked(api);
const admin = { id: 1, role: 'admin', name: 'Admin', first_name: 'A', last_name: 'Admin', email: 'admin@example.com' };

beforeEach(() => {
  apiMock.mockReset();
});

describe('Operations integrations', () => {
  it('loads and displays WIW readiness and all eight documents', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === 'integrations/wiw/status/') return Promise.resolve({ configured: true, installed_count: 6, total_count: 8 });
      if (path === 'document-catalog/') return Promise.resolve(Array.from({ length: 8 }, (_, index) => ({ id: index + 1, name: `Dokument ${index + 1}` })));
      if (path === 'operations/') return Promise.resolve({ notifications: [], availabilities: [], swaps: [], upcoming_shifts: [] });
      if (path === 'workers/') return Promise.resolve([]);
      if (path === 'clients/') return Promise.resolve([]);
      return Promise.resolve({});
    });

    render(<Operations user={admin as any} />);

    await waitFor(() => expect(screen.getByText('6/8 installiert')).toBeInTheDocument());
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
    await waitFor(() => expect(screen.getByText('Anfragen')).toBeInTheDocument());
    expect(screen.queryByTestId('wiw-integration-panel')).not.toBeInTheDocument();
  });
});

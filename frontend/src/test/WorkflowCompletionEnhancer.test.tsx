import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMock = vi.fn();
vi.mock('../api', () => ({ api: (...args: any[]) => apiMock(...args) }));

import WorkflowCompletionEnhancer from '../WorkflowCompletionEnhancer';

describe('WorkflowCompletionEnhancer', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="root"></div>';
    apiMock.mockReset();
  });

  it('adds a real Akte button per worker and opens grouped file data', async () => {
    document.body.innerHTML += `
      <div class="title"><h1>Personal & Kunden</h1></div>
      <div class="panel"><h3>Mitarbeiter</h3><div class="row"><div>Anna Becker MA-001</div></div></div>
      <div class="panel"><h3>Kunden</h3></div>`;

    apiMock.mockImplementation((path: string) => {
      if (path === 'auth/me/') return Promise.resolve({ id: 'admin', role: 'admin' });
      if (path.startsWith('workers/?')) return Promise.resolve({ results: [{ id: 'worker-1', employee_number: 'MA-001', user_detail: { name: 'Anna Becker' } }] });
      if (path.startsWith('clients/?')) return Promise.resolve({ results: [] });
      if (path === 'workers/worker-1/akte/') return Promise.resolve({
        kind: 'worker', title: 'Anna Becker', number: 'MA-001', summary: { contracts: 1, documents: 1, payroll: 1, shifts: 2 },
        contracts: [{ id: 'c1', title: 'Arbeitsvertrag', template_name: 'AV', status: 'signed', updated_at: '2026-08-21', pdf: '/media/av.pdf' }],
        document_folders: [{ key: 'certificates', label: 'Nachweise', count: 1, items: [{ id: 'd1', title: 'Nachweis', created_at: '2026-08-20', visibility: 'worker', file: '/media/doc.pdf' }] }],
        payroll: [{ id: 'p1', period: '2026-08-01', gross_amount: '1000.00', document: '/media/payroll.pdf' }],
        shifts: [],
      });
      return Promise.resolve({ results: [] });
    });

    render(<WorkflowCompletionEnhancer />);
    const button = await screen.findByRole('button', { name: 'Akte' });
    fireEvent.click(button);
    expect(await screen.findByTestId('akte-modal')).toBeInTheDocument();
    expect(screen.getByText('Arbeitsvertrag')).toBeInTheDocument();
    expect(screen.getByText('Nachweise')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Lohnabrechnungen' })).toBeInTheDocument();
  });

  it('lets a client attach a function sheet to an existing order', async () => {
    document.body.innerHTML += '<div class="title"><h1>Aufträge</h1><p>Veranstaltungen</p></div>';
    const order = { id: 'order-1', title: 'Sommerfest', starts_at: '2026-09-01T18:00:00Z', description: 'Bestehend' };

    apiMock.mockImplementation((path: string, options?: RequestInit) => {
      if (path === 'auth/me/') return Promise.resolve({ id: 'client', role: 'client' });
      if (path.startsWith('orders/?')) return Promise.resolve({ results: [order] });
      if (path === 'orders/order-1/' && options?.method === 'PATCH') return Promise.resolve({ ...order, attachment: '/media/functions.pdf' });
      return Promise.resolve({ results: [] });
    });

    render(<WorkflowCompletionEnhancer />);
    fireEvent.click(await screen.findByTestId('order-upload-open'));
    expect(await screen.findByTestId('order-upload-modal')).toBeInTheDocument();

    const file = new File(['%PDF-1.4'], 'functions.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByTestId('order-file-input'), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText('Functions und Hinweise'), { target: { value: '4 Service, 2 Runner' } });
    fireEvent.click(screen.getByRole('button', { name: 'Datei hochladen' }));

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      'orders/order-1/',
      expect.objectContaining({ method: 'PATCH', body: expect.any(FormData) }),
    ));
    const call = apiMock.mock.calls.find((item) => item[0] === 'orders/order-1/');
    const body = call?.[1]?.body as FormData;
    expect(body.get('attachment')).toBe(file);
    expect(String(body.get('description'))).toContain('4 Service, 2 Runner');
  });
});
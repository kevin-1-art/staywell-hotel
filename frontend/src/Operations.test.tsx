import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import Operations, { type Section } from './Operations';
import { apiRequest } from './api';

const staffAccount = { id: 'staff-1', email: 'desk@example.com', full_name: 'Riley Desk', role: 'front_desk', is_active: true, created_at: '2026-10-01T08:00:00Z', deleted_at: null };

vi.mock('./api', () => ({
  apiDownload: vi.fn(),
  apiRequest: vi.fn(async (path: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET';
    if (path === '/dashboard') return {
      date: '2026-09-30', arrivals: 4, departures: 3, in_house: 52,
      sellable_rooms: 80, occupancy_percent: 65, revenue_ugx: 2500000,
      adr_ugx: 240000, revpar_ugx: 156000, dirty_rooms: 2, open_housekeeping_tasks: 2,
    };
    if (path === '/admin/roles') return [
      { key: 'admin', label: 'Administrator', description: 'All access', permissions: ['Manage staff'] },
      { key: 'manager', label: 'Manager', description: 'Manage operations', permissions: ['Reports'] },
      { key: 'front_desk', label: 'Front Desk', description: 'Guest services', permissions: ['Reservations'] },
      { key: 'housekeeping', label: 'Housekeeping', description: 'Room turns', permissions: ['Tasks'] },
      { key: 'accountant', label: 'Accountant', description: 'Finance', permissions: ['Billing'] },
    ];
    if (path.startsWith('/admin/users')) {
      if (method === 'GET' && /^\/admin\/users\/[^?]+$/.test(path)) return staffAccount;
      if (method === 'PATCH') return { ...staffAccount, ...(JSON.parse(String(init.body)) as Record<string, unknown>) };
      if (method === 'DELETE') return { ...staffAccount, is_active: false, deleted_at: '2026-10-01T09:00:00Z' };
      return { items: [staffAccount], total: 1, limit: 200, offset: 0 };
    }
    if (path.startsWith('/audit-logs')) return {
      items: [{ id: 'event-1', actor_id: 'admin-1', actor_name: 'Avery Admin', actor_email: 'admin@example.com', action: 'user.created', entity_type: 'user', entity_id: 'user-2', details: { role: 'front_desk' }, created_at: '2026-10-01T08:00:00+00:00' }],
      total: 1, limit: 50, offset: 0,
    };
    if (path.startsWith('/rooms')) return { items: [], total: 0, limit: 200, offset: 0 };
    if (path.startsWith('/housekeeping')) return { items: [], total: 0, limit: 200, offset: 0 };
    if (path.startsWith('/reservations')) return { items: [], total: 0, limit: 200, offset: 0 };
    if (path === '/inventory' && method === 'POST') return { id: 'inventory-1', ...(JSON.parse(String(init.body)) as Record<string, unknown>) };
    if (path.includes('include_archived=true')) return { items: [], total: 0, limit: 200, offset: 0 };
    if (path.startsWith('/inventory') && method === 'DELETE') return { id: 'inventory-zero', archived_at: '2026-10-01T09:00:00Z' };
    if (path.startsWith('/inventory')) return { items: [
      { id: 'inventory-zero', sku: 'ZERO-01', name: 'Retired item', unit: 'piece', quantity_on_hand: 0, reorder_level: 3, unit_cost_ugx: 1000, low_stock: true },
      { id: 'inventory-stocked', sku: 'LIVE-01', name: 'Active item', unit: 'piece', quantity_on_hand: 5, reorder_level: 3, unit_cost_ugx: 2000, low_stock: false },
    ], total: 2, limit: 200, offset: 0 };
    return { items: [] };
  }),
}));

function renderWorkspace(role: 'admin' | 'manager' | 'housekeeping' = 'manager') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Workspace() {
    const [section, setSection] = useState<Section>('overview');
    return <Operations role={role} section={section} setSection={setSection} userId={role === 'admin' ? 'admin-test' : 'staff-test'} userName="Morgan Manager" onSignOut={vi.fn()} />;
  }
  return render(
    <QueryClientProvider client={client}>
      <Workspace />
    </QueryClientProvider>,
  );
}

describe('hotel operations workspace', () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    localStorage.clear();
  });

  it('renders live dashboard metrics returned by the API', async () => {
    renderWorkspace();
    expect(await screen.findByText('65%')).toBeInTheDocument();
    expect(screen.getByText('52')).toBeInTheDocument();
    expect(screen.getByText(/2,500,000/)).toBeInTheDocument();
  });

  it('limits housekeeping navigation to permitted sections', async () => {
    renderWorkspace('housekeeping');
    expect(await screen.findByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Front desk' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reports' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Housekeeping' })).toBeInTheDocument();
  });

  it('persists the selected dark theme', async () => {
    renderWorkspace();
    await screen.findByText('65%');
    fireEvent.click(screen.getByRole('button', { name: 'Use dark theme' }));
    expect(screen.getByRole('main')).toHaveClass('theme-dark');
    expect(localStorage.getItem('staywell-theme')).toBe('dark');
  });

  it('shows staff management only to administrators', async () => {
    renderWorkspace('manager');
    expect(screen.queryByRole('button', { name: 'Team & access' })).not.toBeInTheDocument();
    cleanup();
    renderWorkspace('admin');
    fireEvent.click(screen.getByRole('button', { name: 'Team & access' }));
    expect(await screen.findByRole('heading', { name: 'Team & access' })).toBeInTheDocument();
    expect(await screen.findByText('Five clear access levels')).toBeInTheDocument();
  });

  it('shows the searchable audit tab only to administrators', async () => {
    renderWorkspace('manager');
    expect(screen.queryByRole('button', { name: 'Audit log' })).not.toBeInTheDocument();
    cleanup();
    renderWorkspace('admin');
    fireEvent.click(screen.getByRole('button', { name: 'Audit log' }));
    expect(await screen.findByRole('heading', { name: 'Audit log' })).toBeInTheDocument();
    expect(await screen.findByText('Avery Admin')).toBeInTheDocument();
    expect(screen.getAllByText('user · created').length).toBeGreaterThan(1);
  });

  it('edits staff profiles through the Admin update endpoint', async () => {
    renderWorkspace('admin');
    fireEvent.click(screen.getByRole('button', { name: 'Team & access' }));
    await screen.findByText('Riley Desk');
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    await screen.findByRole('heading', { name: 'Riley Desk' });
    expect(apiRequest).toHaveBeenCalledWith('/admin/users/staff-1');
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Riley Updated' } });
    fireEvent.change(screen.getByLabelText('Work email'), { target: { value: 'riley.updated@example.com' } });
    fireEvent.change(screen.getByLabelText('Reset password (optional)'), { target: { value: 'New-Password-42!' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByText('Riley Updated’s account has been updated.')).toBeInTheDocument();
    expect(apiRequest).toHaveBeenCalledWith('/admin/users/staff-1', expect.objectContaining({ method: 'PATCH' }));
  });

  it('creates an inventory item through the inventory endpoint', async () => {
    renderWorkspace('manager');
    fireEvent.click(screen.getByRole('button', { name: 'Inventory' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Add item' }));
    fireEvent.change(screen.getByLabelText('Item code'), { target: { value: 'TOWEL-01' } });
    fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Bath towel' } });
    fireEvent.change(screen.getByLabelText('Quantity on hand'), { target: { value: '24' } });
    fireEvent.change(screen.getByLabelText('Reorder threshold'), { target: { value: '8' } });
    fireEvent.change(screen.getByLabelText('Unit cost (UGX)'), { target: { value: '18000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add to inventory' }));
    expect(await screen.findByText('Bath towel was added to inventory.')).toBeInTheDocument();
    expect(apiRequest).toHaveBeenCalledWith('/inventory', expect.objectContaining({ method: 'POST' }));
  });

  it('archives only zero-stock inventory through the Delete endpoint', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWorkspace('manager');
    fireEvent.click(screen.getByRole('button', { name: 'Inventory' }));
    const remove = await screen.findByRole('button', { name: 'Remove Retired item' });
    expect(remove).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Remove Active item' })).toBeDisabled();
    fireEvent.click(remove);
    expect(await screen.findByText('Retired item was removed from active inventory and archived.')).toBeInTheDocument();
    expect(apiRequest).toHaveBeenCalledWith('/inventory/inventory-zero', expect.objectContaining({ method: 'DELETE' }));
  });
});
import { lazy, Suspense, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm, useWatch } from 'react-hook-form';
import { LogOut, Moon, Plus, Search, Sun, Trash2, X } from 'lucide-react';
import { z } from 'zod';
import { apiDownload, apiRequest } from './api';
import type { Role } from './types';

export type Section = 'overview' | 'reservations' | 'rooms' | 'housekeeping' | 'reports' | 'inventory' | 'staff' | 'audit';
type Room = { id: string; number: string; floor: number; room_type_id: string; room_type_name: string; status: string };
type Guest = { id: string; first_name: string; last_name: string; email: string | null; phone: string | null; is_vip: boolean; is_blacklisted: boolean };
type Reservation = { id: string; confirmation_code: string; guest_id: string; guest_name: string; room_id: string; room_number: string; check_in: string; check_out: string; status: string; source: string; nightly_rate_ugx: number; deposit_ugx: number };
type Page<T> = { items: T[]; total: number; limit: number; offset: number };
type Dashboard = { date: string; arrivals: number; departures: number; in_house: number; sellable_rooms: number; occupancy_percent: number; revenue_ugx?: number; adr_ugx?: number; revpar_ugx?: number; dirty_rooms: number; open_housekeeping_tasks: number };
type Task = { id: string; room_number: string; floor: number; status: string; notes: string; assigned_to_name: string | null };
type Inventory = { id: string; sku: string; name: string; unit: string; quantity_on_hand: number; reorder_level: number; unit_cost_ugx: number; low_stock: boolean; archived_at?: string | null };
const Reports = lazy(() => import('./Reports'));
const Staff = lazy(() => import('./Staff'));
const Audit = lazy(() => import('./Audit'));

const bookingSchema = z.object({
  guest_id: z.string().min(1, 'Choose a guest'),
  room_id: z.string().min(1, 'Choose an available room'),
  check_in: z.string().min(1, 'Choose a check-in date'),
  check_out: z.string().min(1, 'Choose a check-out date'),
  nightly_rate_ugx: z.coerce.number().int().min(0).optional(),
  deposit_ugx: z.coerce.number().int().min(0),
  source: z.string().min(1),
  promo_code: z.string().optional(),
  company_name: z.string().optional(),
});
type BookingForm = z.input<typeof bookingSchema>;
type BookingPayload = z.output<typeof bookingSchema>;
const guestSchema = z.object({ first_name: z.string().min(1), last_name: z.string().min(1), email: z.email().or(z.literal('')), phone: z.string().optional() });
type GuestForm = z.infer<typeof guestSchema>;
const inventorySchema = z.object({
  sku: z.string().trim().min(2, 'Enter an item code').max(40),
  name: z.string().trim().min(2, 'Enter an item name').max(120),
  unit: z.string().trim().min(1, 'Enter a stock unit').max(24),
  quantity_on_hand: z.coerce.number().int().min(0),
  reorder_level: z.coerce.number().int().min(0),
  unit_cost_ugx: z.coerce.number().int().min(0),
});
type InventoryForm = z.input<typeof inventorySchema>;
type InventoryPayload = z.output<typeof inventorySchema>;

const money = (amount = 0) => new Intl.NumberFormat('en-UG', { style: 'currency', currency: 'UGX', maximumFractionDigits: 0 }).format(amount);
const today = () => new Date().toISOString().slice(0, 10);
const roleAllowed = (role: Role, roles: Role[]) => roles.includes(role);

export const sectionAccess: Record<Section, Role[]> = {
  overview: ['admin', 'manager', 'front_desk', 'housekeeping', 'accountant'],
  reservations: ['admin', 'manager', 'front_desk', 'accountant'],
  rooms: ['admin', 'manager', 'front_desk', 'housekeeping'],
  housekeeping: ['admin', 'manager', 'front_desk', 'housekeeping'],
  reports: ['admin', 'manager', 'front_desk', 'accountant'],
  inventory: ['admin', 'manager', 'accountant'],
  staff: ['admin'],
  audit: ['admin'],
};

function useHotelMutation(key: string[], path: string, method = 'POST') {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body?: unknown) => apiRequest(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: key }),
  });
}

export default function Operations({ role, section, setSection, userId, userName, onSignOut }: { role: Role; section: Section; setSection: (section: Section) => void; userId: string; userName: string; onSignOut: () => void }) {
  const [globalSearch, setGlobalSearch] = useState('');
  const [dark, setDark] = useState(() => localStorage.getItem('staywell-theme') === 'dark');
  const [notice, setNotice] = useState('');
  function toggleTheme() {
    const next = !dark;
    setDark(next);
    localStorage.setItem('staywell-theme', next ? 'dark' : 'light');
  }
  const links: { id: Section; label: string }[] = [
    { id: 'overview', label: 'Overview' }, { id: 'reservations', label: 'Front desk' },
    { id: 'rooms', label: 'Room board' }, { id: 'housekeeping', label: 'Housekeeping' },
    { id: 'reports', label: 'Reports' }, { id: 'inventory', label: 'Inventory' },
    { id: 'staff', label: 'Team & access' },
    { id: 'audit', label: 'Audit log' },
  ];
  const visibleLinks = links.filter((link) => roleAllowed(role, sectionAccess[link.id]));
  const activeSection = visibleLinks.some((link) => link.id === section) ? section : 'overview';
  const pageTitle = links.find((link) => link.id === activeSection)?.label ?? 'Overview';
  const roomQuery = useQuery({ queryKey: ['rooms'], queryFn: () => apiRequest<Page<Room>>('/rooms?limit=200') });
  const reservationsQuery = useQuery({ queryKey: ['reservations'], queryFn: () => apiRequest<Page<Reservation>>('/reservations?limit=200'), enabled: role !== 'housekeeping' });
  const dashboardQuery = useQuery({ queryKey: ['dashboard'], queryFn: () => apiRequest<Dashboard>('/dashboard'), refetchInterval: 60_000 });
  const housekeepingQuery = useQuery({ queryKey: ['housekeeping'], queryFn: () => apiRequest<Page<Task>>('/housekeeping?limit=200'), enabled: roleAllowed(role, sectionAccess.housekeeping) });
  const inventoryQuery = useQuery({ queryKey: ['inventory'], queryFn: () => apiRequest<Page<Inventory>>('/inventory?limit=200'), enabled: activeSection === 'inventory' });
  const visibleReservations = useMemo(() => (reservationsQuery.data?.items ?? []).filter((reservation) => {
    const query = globalSearch.trim().toLowerCase();
    return !query || `${reservation.guest_name} ${reservation.room_number} ${reservation.confirmation_code}`.toLowerCase().includes(query);
  }), [globalSearch, reservationsQuery.data]);

  async function downloadReport(type: string, format: 'csv' | 'pdf') {
    try {
      const from = new Date();
      from.setDate(from.getDate() - 30);
      const url = URL.createObjectURL(await apiDownload(`/reports/${type}?from_date=${from.toISOString().slice(0, 10)}&to_date=${today()}&export=${format}`));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${type}-last-30-days.${format}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Report export failed');
    }
  }

  return (
    <main className={`workspace ${dark ? 'theme-dark' : ''}`}>
      <aside className="sidebar">
        <div className="sidebar-brand"><span className="brand-mark">S</span><span>STAYWELL<small>HOTEL OPERATIONS</small></span></div>
        <div className="property-switch"><span className="property-icon">K</span><span>Staywell Kampala<small>PROPERTY WORKSPACE</small></span></div>
        <nav aria-label="Main navigation"><span className="nav-caption">WORKSPACE</span>{visibleLinks.map((link) => <button key={link.id} className={`nav-link ${activeSection === link.id ? 'active' : ''}`} onClick={() => setSection(link.id)}><span className="nav-dot" />{link.label}</button>)}</nav>
        <div className="sidebar-bottom"><span className="online-label"><i /> LIVE SYSTEM</span><span className="api-version">Staywell PMS · v1.0</span></div>
      </aside>
      <section className="main-panel">
        <header className="topbar">
          <span className="crumb">Workspace <b>/</b> {pageTitle}</span>
          <label className="global-search"><Search size={15} /><input aria-label="Search guests and reservations" value={globalSearch} onChange={(event) => setGlobalSearch(event.target.value)} placeholder="Search guest, room, confirmation" /></label>
          <button className="icon-button theme-toggle" onClick={toggleTheme} aria-label={dark ? 'Use light theme' : 'Use dark theme'} title={dark ? 'Light mode' : 'Dark mode'}>{dark ? <Sun size={16} /> : <Moon size={16} />}</button>
          <span className="role-chip">{role.replace('_', ' ')}</span>
          <span className="topbar-user">{userName}</span>
          <button className="icon-button" onClick={onSignOut} aria-label="Sign out" title="Sign out"><LogOut size={16} /></button>
        </header>
        <div className="dashboard-content">
          {notice && <div className="toast" role="status">{notice}<button aria-label="Dismiss" onClick={() => setNotice('')}><X size={15} /></button></div>}
          {activeSection === 'overview' && <Overview dashboard={dashboardQuery.data} rooms={roomQuery.data?.items ?? []} tasks={housekeepingQuery.data?.items ?? []} loading={dashboardQuery.isLoading} />}
          {activeSection === 'reservations' && <Reservations role={role} reservations={visibleReservations} loading={reservationsQuery.isLoading} onNotice={setNotice} />}
          {activeSection === 'rooms' && <RoomBoard rooms={roomQuery.data?.items ?? []} reservations={reservationsQuery.data?.items ?? []} loading={roomQuery.isLoading} onNotice={setNotice} />}
          {activeSection === 'housekeeping' && <Housekeeping tasks={housekeepingQuery.data?.items ?? []} loading={housekeepingQuery.isLoading} onNotice={setNotice} />}
          {activeSection === 'reports' && <Suspense fallback={<div className="loading-state">Loading reports…</div>}><Reports onDownload={downloadReport} /></Suspense>}
          {activeSection === 'inventory' && <Inventory role={role} items={inventoryQuery.data?.items ?? []} loading={inventoryQuery.isLoading} onNotice={setNotice} />}
          {activeSection === 'staff' && <Suspense fallback={<div className="loading-state">Loading staff…</div>}><Staff currentUserId={userId} onNotice={setNotice} /></Suspense>}
          {activeSection === 'audit' && <Suspense fallback={<div className="loading-state">Loading audit log…</div>}><Audit /></Suspense>}
          {dashboardQuery.isError && <p className="error-banner" role="alert">Unable to load hotel data. Check the service connection and retry.</p>}
          <div className="bottom-note"><span>STAYWELL · OPERATIONS</span><span>ALL AMOUNTS IN UGX</span></div>
        </div>
      </section>
    </main>
  );
}

function Overview({ dashboard, rooms, tasks, loading }: { dashboard?: Dashboard; rooms: Room[]; tasks: Task[]; loading: boolean }) {
  const arrivals = dashboard?.arrivals ?? 0;
  const dirty = rooms.filter((room) => room.status === 'dirty').length;
  return <>
    <div className="welcome-row"><div><span className="eyebrow">{new Intl.DateTimeFormat('en-UG', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'Africa/Kampala' }).format(new Date()).toUpperCase()} · KAMPALA</span><h1>Your hotel, in rhythm.</h1><p className="muted">Today’s operating picture.</p></div><div className="date-stamp"><span>LOCAL TIME</span><strong>{new Intl.DateTimeFormat('en-UG', { hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Kampala' }).format(new Date())}</strong><small>Kampala, EAT</small></div></div>
    {loading ? <div className="loading-state" role="status">Loading today’s figures…</div> : <div className="metric-grid" aria-label="Hotel overview">
      <Metric label="ARRIVALS" value={arrivals} caption="Expected today" />
      <Metric label="DEPARTURES" value={dashboard?.departures ?? 0} caption="Expected today" />
      <Metric label="IN-HOUSE" value={dashboard?.in_house ?? 0} caption="Current guests" />
      <Metric label="OCCUPANCY" value={`${dashboard?.occupancy_percent ?? 0}%`} caption={`${dashboard?.sellable_rooms ?? 0} sellable rooms`} dark />
      <Metric label="REVENUE TODAY" value={money(dashboard?.revenue_ugx)} caption="Collected less refunds" />
      <Metric label="ADR" value={money(dashboard?.adr_ugx)} caption="In-house room rate" />
      <Metric label="REVPAR" value={money(dashboard?.revpar_ugx)} caption="Revenue per sellable room" />
      <Metric label="TURNOVER" value={dirty} caption={`${dashboard?.open_housekeeping_tasks ?? 0} open tasks`} />
    </div>}
    <div className="overview-lower"><section className="panel"><div className="panel-heading"><div><span className="eyebrow">ROOM STATUS</span><h2>Today’s floor pulse</h2></div><span className="panel-count">{rooms.length} rooms</span></div><div className="status-legend">{['available', 'occupied', 'dirty', 'cleaning', 'inspected', 'out_of_order'].map((status) => <span key={status}><i className={`status-dot status-${status}`} />{status.replace('_', ' ')}</span>)}</div><div className="mini-room-grid">{rooms.slice(0, 32).map((room) => <span key={room.id} className={`mini-room status-${room.status}`} title={`Room ${room.number}: ${room.status}`}>{room.number}</span>)}</div></section><section className="panel arrivals-panel"><div className="panel-heading"><div><span className="eyebrow">ARRIVALS</span><h2>Expected today</h2></div><span className="feature-icon">{arrivals}</span></div><p className="muted">{arrivals ? `${arrivals} guests are due to arrive.` : 'No arrivals scheduled for today.'}</p><div className="turnover-callout"><strong>{dirty}</strong><span>rooms waiting for housekeeping</span></div><ul className="task-summary">{tasks.filter((task) => task.status !== 'completed').slice(0, 3).map((task) => <li key={task.id}>Room {task.room_number}<span>{task.status.replace('_', ' ')}</span></li>)}</ul></section></div>
  </>;
}

function Metric({ label, value, caption, dark = false }: { label: string; value: string | number; caption: string; dark?: boolean }) {
  return <article className={`metric-card ${dark ? 'metric-dark' : ''}`}><span>{label}</span><strong>{value}</strong><small>{caption}</small></article>;
}

function Reservations({ role, reservations, loading, onNotice }: { role: Role; reservations: Reservation[]; loading: boolean; onNotice: (message: string) => void }) {
  const [view, setView] = useState<'list' | 'timeline'>('list');
  const [showBooking, setShowBooking] = useState(false);
  const [expanded, setExpanded] = useState('');
  const [rangeStart, setRangeStart] = useState(today());
  const [addingGuest, setAddingGuest] = useState(false);
  const bookingForm = useForm<BookingForm, unknown, BookingPayload>({ resolver: zodResolver(bookingSchema), defaultValues: { check_in: today(), check_out: new Date(Date.now() + 86_400_000).toISOString().slice(0, 10), deposit_ugx: 0, source: 'direct' } });
  const guestForm = useForm<GuestForm>({ resolver: zodResolver(guestSchema) });
  const dates = useWatch({ control: bookingForm.control, name: ['check_in', 'check_out'] });
  const [checkInDate, checkOutDate] = dates;
  const selectedRoomId = useWatch({ control: bookingForm.control, name: 'room_id' });
  const promoCode = useWatch({ control: bookingForm.control, name: 'promo_code' });
  const companyName = useWatch({ control: bookingForm.control, name: 'company_name' });
  const guestQuery = useQuery({ queryKey: ['guests'], queryFn: () => apiRequest<Page<Guest>>('/guests?limit=200'), enabled: showBooking || expanded !== '' });
  const availableQuery = useQuery({
    queryKey: ['availability', checkInDate, checkOutDate],
    queryFn: () => apiRequest<Room[]>(`/reservations/availability?check_in=${checkInDate}&check_out=${checkOutDate}`),
    enabled: showBooking && Boolean(checkInDate && checkOutDate && checkOutDate > checkInDate),
  });
  const selectedRoom = availableQuery.data?.find((room) => room.id === selectedRoomId);
  const quoteQuery = useQuery({
    queryKey: ['rate-quote', selectedRoom?.room_type_id, checkInDate, checkOutDate, promoCode, companyName],
    queryFn: () => apiRequest<{ average_nightly_rate_ugx: number; total_ugx: number; subtotal_ugx: number; service_charge_ugx: number; tax_ugx: number }>(
      '/reservations/rate-quote',
      { method: 'POST', body: JSON.stringify({ room_type_id: selectedRoom?.room_type_id, check_in: checkInDate, check_out: checkOutDate, promo_code: promoCode || null, company_name: companyName || null }) },
    ),
    enabled: showBooking && Boolean(selectedRoom && checkInDate && checkOutDate && checkOutDate > checkInDate),
  });
  const client = useQueryClient();
  const createBooking = useMutation({ mutationFn: (data: BookingPayload) => apiRequest<Reservation>('/reservations', { method: 'POST', body: JSON.stringify(data) }), onSuccess: () => { client.invalidateQueries({ queryKey: ['reservations'] }); client.invalidateQueries({ queryKey: ['availability'] }); setShowBooking(false); bookingForm.reset(); onNotice('Reservation confirmed.'); }, onError: (error: Error) => onNotice(error.message) });
  const createGuest = useMutation({ mutationFn: (data: GuestForm) => apiRequest<Guest>('/guests', { method: 'POST', body: JSON.stringify({ ...data, email: data.email || null }) }), onSuccess: (guest) => { client.invalidateQueries({ queryKey: ['guests'] }); bookingForm.setValue('guest_id', guest.id); setAddingGuest(false); guestForm.reset(); }, onError: (error: Error) => onNotice(error.message) });
  const activeDays = Array.from({ length: 7 }, (_, index) => { const day = new Date(`${rangeStart}T12:00:00`); day.setDate(day.getDate() + index); return day.toISOString().slice(0, 10); });

  async function checkInReservation(reservation: Reservation) {
    const documentNumber = window.prompt('Government ID or passport number');
    if (!documentNumber) return;
    try {
      await apiRequest(`/reservations/${reservation.id}/check-in`, { method: 'POST', body: JSON.stringify({ id_document_type: 'national_id', id_document_number: documentNumber }) });
      await client.invalidateQueries({ queryKey: ['reservations', 'rooms', 'dashboard'] });
      onNotice(`Room ${reservation.room_number} checked in.`);
    } catch (error) { onNotice(error instanceof Error ? error.message : 'Check-in failed'); }
  }

  async function quickAction(path: string, body: unknown, message: string) {
    try { await apiRequest(path, { method: 'POST', body: JSON.stringify(body) }); await client.invalidateQueries({ queryKey: ['reservations', 'rooms', 'dashboard', 'housekeeping'] }); onNotice(message); }
    catch (error) { onNotice(error instanceof Error ? error.message : 'Action failed'); }
  }

  return <>
    <div className="page-title-row"><div><span className="eyebrow">FRONT DESK</span><h1>Reservations</h1><p className="muted">Search, book, and look after every arrival.</p></div><button className="primary-button compact" onClick={() => setShowBooking(true)}><Plus size={16} /> New reservation</button></div>
    <div className="toolbar"><div className="segmented" role="tablist" aria-label="Reservation view"><button role="tab" aria-selected={view === 'list'} className={view === 'list' ? 'selected' : ''} onClick={() => setView('list')}>List</button><button role="tab" aria-selected={view === 'timeline'} className={view === 'timeline' ? 'selected' : ''} onClick={() => setView('timeline')}>7-day timeline</button></div><label className="date-field">Week of <input type="date" value={rangeStart} onChange={(event) => setRangeStart(event.target.value)} /></label></div>
    {showBooking && <section className="panel booking-panel"><div className="panel-heading"><div><span className="eyebrow">NEW BOOKING</span><h2>Reserve a room</h2></div><button className="icon-button" onClick={() => setShowBooking(false)} aria-label="Close reservation form"><X size={16} /></button></div>
      <form className="form-grid" onSubmit={bookingForm.handleSubmit((values) => createBooking.mutate({ ...values, nightly_rate_ugx: quoteQuery.data?.average_nightly_rate_ugx }))}>
        <label>Check-in<input type="date" {...bookingForm.register('check_in')} />{bookingForm.formState.errors.check_in && <small className="field-error">{bookingForm.formState.errors.check_in.message}</small>}</label>
        <label>Check-out<input type="date" {...bookingForm.register('check_out')} /></label>
        <label className="guest-select">Guest<select {...bookingForm.register('guest_id')}><option value="">Choose a guest</option>{guestQuery.data?.items.map((guest) => <option key={guest.id} value={guest.id}>{guest.first_name} {guest.last_name}{guest.is_vip ? ' · VIP' : ''}</option>)}</select></label>
        <button type="button" className="text-button" onClick={() => setAddingGuest(true)}><Plus size={14} /> Add guest</button>
        <label>Available room<select {...bookingForm.register('room_id')}><option value="">Choose a room</option>{availableQuery.data?.map((room) => <option key={room.id} value={room.id}>{room.number} · {room.room_type_name}</option>)}</select></label>
        <label>Deposit (UGX)<input type="number" min="0" step="1" {...bookingForm.register('deposit_ugx')} /></label>
        <label>Booking source<select {...bookingForm.register('source')}><option value="direct">Direct</option><option value="corporate">Corporate</option><option value="ota">OTA</option><option value="walk_in">Walk-in</option></select></label>
        <label>Company<input {...bookingForm.register('company_name')} placeholder="Corporate booking" /></label>
        <label>Promo code<input {...bookingForm.register('promo_code')} placeholder="Optional" /></label>
        <div className="quote-summary"><span>Nightly <strong>{money(quoteQuery.data?.average_nightly_rate_ugx)}</strong></span><span>Stay total <strong>{money(quoteQuery.data?.total_ugx)}</strong></span><small>Includes {money(quoteQuery.data?.service_charge_ugx)} service and {money(quoteQuery.data?.tax_ugx)} tax</small></div>
        {(availableQuery.isFetching || quoteQuery.isFetching) && <span className="muted">Checking availability and rate…</span>}
        <button className="primary-button compact" type="submit" disabled={createBooking.isPending || !quoteQuery.data}>Confirm reservation</button>
      </form>
      {addingGuest && <form className="inline-guest-form" onSubmit={guestForm.handleSubmit((data) => createGuest.mutate(data))}><div className="panel-heading"><h2>New guest</h2><button type="button" className="icon-button" onClick={() => setAddingGuest(false)} aria-label="Close guest form"><X size={15} /></button></div><label>First name<input {...guestForm.register('first_name')} /></label><label>Last name<input {...guestForm.register('last_name')} /></label><label>Email<input type="email" {...guestForm.register('email')} /></label><label>Phone<input {...guestForm.register('phone')} /></label><button className="secondary-button" type="submit">Save guest</button></form>}
    </section>}
    {view === 'timeline' ? <div className="timeline-wrap"><div className="timeline-head"><span>GUEST / ROOM</span>{activeDays.map((day) => <span key={day}>{new Intl.DateTimeFormat('en-UG', { weekday: 'short', day: 'numeric' }).format(new Date(`${day}T12:00:00`))}</span>)}</div>{reservations.filter((row) => row.status === 'confirmed' || row.status === 'checked_in').map((row) => <div className="timeline-row" key={row.id}><span className="timeline-guest">{row.guest_name}<small>{row.room_number}</small></span><div className="timeline-days">{activeDays.map((day) => { const active = day >= row.check_in && day < row.check_out; return <span key={day} className={active ? `timeline-stay ${row.status}` : ''} title={active ? `${row.guest_name} · ${row.room_number}` : undefined}>{active && day === row.check_in ? row.confirmation_code : ''}</span>; })}</div></div>)}</div> : <div className="table-wrap"><table><thead><tr><th>Confirmation</th><th>Guest</th><th>Room</th><th>Stay</th><th>Source</th><th>Status</th><th /></tr></thead><tbody>{loading ? <tr><td colSpan={7}><div className="loading-state">Loading reservations…</div></td></tr> : reservations.map((reservation) => <FragmentReservation key={reservation.id} role={role} reservation={reservation} expanded={expanded === reservation.id} onToggle={() => setExpanded(expanded === reservation.id ? '' : reservation.id)} onCheckIn={() => void checkInReservation(reservation)} onAction={quickAction} />)}{!loading && reservations.length === 0 && <tr><td colSpan={7}><div className="empty-state">No reservations match this search.</div></td></tr>}</tbody></table></div>}
  </>;
}

function FragmentReservation({ role, reservation, expanded, onToggle, onCheckIn, onAction }: { role: Role; reservation: Reservation; expanded: boolean; onToggle: () => void; onCheckIn: () => void; onAction: (path: string, body: unknown, message: string) => Promise<void> }) {
  const [charge, setCharge] = useState('');
  const [chargeAmount, setChargeAmount] = useState('');
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [lateFee, setLateFee] = useState('0');
  const [overrideReason, setOverrideReason] = useState('');
  const folioQuery = useQuery({ queryKey: ['folio', reservation.id], queryFn: () => apiRequest<{ id: string; invoice_number: number | null; outstanding_ugx: number }>(`/reservations/${reservation.id}/folio`), enabled: expanded && reservation.status === 'checked_in' });
  const managerCanOverride = role === 'admin' || role === 'manager';
  const canMarkNoShow = reservation.status === 'confirmed' && reservation.check_in <= today();
  return <>
    <tr><td><span className="code-label">{reservation.confirmation_code}</span></td><td>{reservation.guest_name}</td><td>{reservation.room_number}</td><td>{reservation.check_in} <span className="muted">to</span> {reservation.check_out}</td><td>{reservation.source.replace('_', ' ')}</td><td><span className={`status-label status-label-${reservation.status}`}>{reservation.status.replace('_', ' ')}</span></td><td>{reservation.status === 'confirmed' ? <><button className="text-button" onClick={onCheckIn}>Check in</button><button className="text-button" onClick={() => { if (window.confirm('Cancel this reservation?')) void onAction(`/reservations/${reservation.id}/cancel`, {}, 'Reservation cancelled.'); }}>Cancel</button>{canMarkNoShow && <button className="text-button" onClick={() => void onAction(`/reservations/${reservation.id}/no-show`, {}, 'Reservation marked no-show.')}>No-show</button>}</> : reservation.status === 'checked_in' ? <button className="text-button" onClick={onToggle}>{expanded ? 'Close folio' : 'Folio'}</button> : null}</td></tr>
    {expanded && <tr><td colSpan={7}><div className="folio-actions"><div className="folio-balance">{folioQuery.isLoading ? 'Loading folio…' : <>Outstanding <strong>{money(folioQuery.data?.outstanding_ugx)}</strong></>}</div><form onSubmit={(event) => { event.preventDefault(); void onAction(`/reservations/${reservation.id}/charges`, { description: charge, category: 'pos', quantity: 1, unit_amount_ugx: Number(chargeAmount) }, 'Charge posted to guest folio.'); setCharge(''); setChargeAmount(''); }}><strong>Post a service charge</strong><input aria-label="Charge description" value={charge} onChange={(event) => setCharge(event.target.value)} placeholder="Restaurant, minibar…" required /><input aria-label="Charge amount in UGX" type="number" min="0" value={chargeAmount} onChange={(event) => setChargeAmount(event.target.value)} placeholder="UGX" required /><button className="secondary-button">Post charge</button></form><form onSubmit={(event) => { event.preventDefault(); void onAction(`/reservations/${reservation.id}/payments`, { amount_ugx: Number(paymentAmount), method: paymentMethod }, 'Payment recorded.'); setPaymentAmount(''); }}><strong>Record a payment</strong><input aria-label="Payment amount in UGX" type="number" min="1" value={paymentAmount} onChange={(event) => setPaymentAmount(event.target.value)} placeholder="UGX" required /><select aria-label="Payment method" value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}><option value="cash">Cash</option><option value="card">Card</option><option value="bank_transfer">Bank transfer</option><option value="mobile_money">Mobile money</option></select><button className="secondary-button">Take payment</button></form>{checkoutOpen ? <form className="checkout-panel" onSubmit={(event) => { event.preventDefault(); void onAction(`/reservations/${reservation.id}/check-out`, { late_check_out_fee_ugx: Number(lateFee), manager_override: Boolean(overrideReason), override_reason: overrideReason || null }, 'Guest checked out. Housekeeping task created.'); setCheckoutOpen(false); }}><strong>Checkout · balance {money(folioQuery.data?.outstanding_ugx)}</strong><label>Late fee (UGX)<input type="number" min="0" value={lateFee} onChange={(event) => setLateFee(event.target.value)} /></label>{managerCanOverride && <label>Override reason<input value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} placeholder="Required to leave a balance" minLength={5} /></label>}<button className="danger-button" type="submit">Complete checkout</button><button className="text-button" type="button" onClick={() => setCheckoutOpen(false)}>Keep stay open</button></form> : <button className="danger-button" onClick={() => setCheckoutOpen(true)}>Check out</button>}</div></td></tr>}
  </>;
}

function RoomBoard({ rooms, reservations, loading, onNotice }: { rooms: Room[]; reservations: Reservation[]; loading: boolean; onNotice: (message: string) => void }) {
  const [floor, setFloor] = useState(1);
  const [dragReservation, setDragReservation] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const client = useQueryClient();
  const floors = [...new Set(rooms.map((room) => room.floor))].sort((a, b) => a - b);
  const staysByRoom = new Map(reservations.filter((reservation) => reservation.status === 'checked_in').map((reservation) => [reservation.room_id, reservation]));
  const filteredRooms = rooms.filter((room) => room.floor === floor && (statusFilter === 'all' || room.status === statusFilter));
  async function moveRoom(room: Room) {
    if (!dragReservation) return;
    try { await apiRequest(`/reservations/${dragReservation}/move-room?room_id=${room.id}`, { method: 'POST' }); await client.invalidateQueries({ queryKey: ['rooms', 'reservations', 'dashboard'] }); onNotice(`Guest moved to room ${room.number}.`); }
    catch (error) { onNotice(error instanceof Error ? error.message : 'Room move failed'); }
    setDragReservation('');
  }
  const changeStatus = useHotelMutation(['rooms'], '', 'PATCH');
  return <>
    <div className="page-title-row"><div><span className="eyebrow">LIVE INVENTORY</span><h1>Room board</h1><p className="muted">{rooms.length} rooms · move in-house guests between ready rooms.</p></div><label className="date-field">Filter<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">All statuses</option>{['available', 'occupied', 'dirty', 'cleaning', 'inspected', 'out_of_order'].map((status) => <option key={status} value={status}>{status.replace('_', ' ')}</option>)}</select></label></div>
    <div className="floor-tabs" role="tablist" aria-label="Room floors">{floors.map((value) => <button key={value} role="tab" aria-selected={floor === value} className={floor === value ? 'selected' : ''} onClick={() => setFloor(value)}>Floor {value}</button>)}</div>
    <div className="status-legend">{['available', 'occupied', 'dirty', 'cleaning', 'inspected', 'out_of_order'].map((status) => <span key={status}><i className={`status-dot status-${status}`} />{status.replace('_', ' ')}</span>)}</div>
    {loading ? <div className="loading-state">Loading room board…</div> : <div className="room-board-grid">{filteredRooms.map((room) => { const stay = staysByRoom.get(room.id); return <button key={room.id} className={`room-tile status-${room.status}`} draggable={Boolean(stay)} onDragStart={(event) => { if (stay) { event.dataTransfer.setData('text/plain', stay.id); setDragReservation(stay.id); } }} onDragEnd={() => setDragReservation('')} onDragOver={(event) => { if (dragReservation) event.preventDefault(); }} onDrop={(event) => { event.preventDefault(); const targetReservation = event.dataTransfer.getData('text/plain'); if (targetReservation) setDragReservation(targetReservation); void moveRoom(room); }} onClick={() => { if (room.status === 'inspected') { void apiRequest(`/rooms/${room.id}/status`, { method: 'PATCH', body: JSON.stringify({ status: 'available' }) }).then(() => client.invalidateQueries({ queryKey: ['rooms'] })).catch((error: Error) => onNotice(error.message)); } }} title={stay ? `Drag guest in room ${room.number} to a ready room` : room.status === 'inspected' ? 'Release inspected room to Available' : `Room ${room.number}: ${room.status}`}><span className="room-number">{room.number}</span><span className="room-type">{room.room_type_name}</span><span className="room-state">{room.status.replace('_', ' ')}</span>{stay && <span className="room-guest">{stay.guest_name}</span>}</button>; })}</div>}
    {changeStatus.isError && <p role="alert" className="error-banner">{(changeStatus.error as Error).message}</p>}
  </>;
}

function Housekeeping({ tasks, loading, onNotice }: { tasks: Task[]; loading: boolean; onNotice: (message: string) => void }) {
  const client = useQueryClient();
  async function advance(task: Task) {
    const action = task.status === 'pending' ? 'start' : task.status === 'in_progress' ? 'complete' : 'release';
    try { await apiRequest(`/housekeeping/${task.id}/${action}`, { method: 'POST' }); await client.invalidateQueries({ queryKey: ['housekeeping', 'rooms', 'dashboard'] }); onNotice(action === 'release' ? `Room ${task.room_number} is available.` : `Room ${task.room_number} task ${action === 'start' ? 'started' : 'completed'}.`); }
    catch (error) { onNotice(error instanceof Error ? error.message : 'Housekeeping action failed'); }
  }
  return <><div className="page-title-row"><div><span className="eyebrow">ROOM TURNOVER</span><h1>Housekeeping</h1><p className="muted">Checkout cleans, assignments and room release.</p></div><span className="health-pill healthy">{tasks.filter((task) => task.status !== 'completed').length} open</span></div><div className="task-list">{loading ? <div className="loading-state">Loading housekeeping tasks…</div> : tasks.map((task) => <article className="task-row" key={task.id}><span className={`feature-icon status-icon-${task.status}`}>{task.room_number}</span><div className="task-main"><strong>Room {task.room_number}<small>Floor {task.floor} · {task.assigned_to_name ?? 'Unassigned'}</small></strong><span className={`status-label status-label-${task.status}`}>{task.status.replace('_', ' ')}</span></div><p>{task.notes}</p><button className="secondary-button" onClick={() => void advance(task)}>{task.status === 'pending' ? 'Start clean' : task.status === 'in_progress' ? 'Mark inspected' : 'Release room'}</button></article>)}{!loading && tasks.length === 0 && <div className="empty-state">No housekeeping tasks are waiting.</div>}</div></>;
}

function Inventory({ role, items, loading, onNotice }: { role: Role; items: Inventory[]; loading: boolean; onNotice: (message: string) => void }) {
  const [showAdd, setShowAdd] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const client = useQueryClient();
  const canManage = roleAllowed(role, ['admin', 'manager']);
  const archivedQuery = useQuery({
    queryKey: ['inventory-archived'],
    queryFn: () => apiRequest<Page<Inventory>>('/inventory?include_archived=true&limit=200'),
    enabled: showArchived && canManage,
  });
  const form = useForm<InventoryForm, unknown, InventoryPayload>({
    resolver: zodResolver(inventorySchema),
    defaultValues: { sku: '', name: '', unit: 'unit', quantity_on_hand: 0, reorder_level: 0, unit_cost_ugx: 0 },
  });
  const createItem = useMutation({
    mutationFn: (value: InventoryPayload) => apiRequest<Inventory>('/inventory', { method: 'POST', body: JSON.stringify(value) }),
    onSuccess: (item) => {
      void client.invalidateQueries({ queryKey: ['inventory'] });
      form.reset();
      setShowAdd(false);
      onNotice(`${item.name} was added to inventory.`);
    },
    onError: (error: Error) => onNotice(error.message),
  });
  const archiveItem = useMutation({
    mutationFn: (item: Inventory) => apiRequest<{ id: string; archived_at: string }>(`/inventory/${item.id}`, { method: 'DELETE' }),
    onSuccess: (_, item) => {
      void client.invalidateQueries({ queryKey: ['inventory'] });
      void client.invalidateQueries({ queryKey: ['inventory-archived'] });
      onNotice(`${item.name} was removed from active inventory and archived.`);
    },
    onError: (error: Error) => onNotice(error.message),
  });
  const visibleItems = showArchived ? archivedQuery.data?.items ?? [] : items;
  return <>
    <div className="page-title-row"><div><span className="eyebrow">PURCHASING & STORES</span><h1>Inventory</h1><p className="muted">Stock on hand and reorder thresholds.</p></div><div className="inventory-heading-actions"><span className="health-pill">{items.filter((item) => item.low_stock).length} low stock</span>{canManage && <><button className="secondary-button" onClick={() => { setShowArchived((value) => !value); setShowAdd(false); }}>{showArchived ? 'Active items' : 'Archived items'}</button><button className="primary-button compact" onClick={() => { setShowArchived(false); setShowAdd((visible) => !visible); }}><Plus size={15} /> Add item</button></>}</div></div>
    {showAdd && canManage && <section className="panel inventory-create-panel"><div className="panel-heading"><div><span className="eyebrow">NEW STOCK ITEM</span><h2>Item details</h2></div><button className="icon-button" aria-label="Close add item form" onClick={() => { setShowAdd(false); form.reset(); }}><X size={15} /></button></div><form className="form-grid" onSubmit={form.handleSubmit((value) => createItem.mutate(value))} noValidate>
      <label>Item code<input aria-invalid={!!form.formState.errors.sku} {...form.register('sku')} />{form.formState.errors.sku && <small className="field-error">{form.formState.errors.sku.message}</small>}</label>
      <label>Item name<input aria-invalid={!!form.formState.errors.name} {...form.register('name')} />{form.formState.errors.name && <small className="field-error">{form.formState.errors.name.message}</small>}</label>
      <label>Unit<select {...form.register('unit')}><option value="unit">Unit</option><option value="piece">Piece</option><option value="bottle">Bottle</option><option value="box">Box</option><option value="kg">Kilogram</option><option value="litre">Litre</option><option value="sachet">Sachet</option></select></label>
      <label>Quantity on hand<input type="number" min="0" step="1" {...form.register('quantity_on_hand')} /></label>
      <label>Reorder threshold<input type="number" min="0" step="1" {...form.register('reorder_level')} /></label>
      <label>Unit cost (UGX)<input type="number" min="0" step="1" {...form.register('unit_cost_ugx')} /></label>
      <div className="inventory-form-actions"><span className="muted">Items at or below the threshold appear as low stock.</span><button className="primary-button compact" type="submit" disabled={createItem.isPending}>{createItem.isPending ? 'Adding…' : 'Add to inventory'}</button></div>
    </form></section>}
    <section className="panel"><div className="table-wrap"><table><thead><tr><th>SKU</th><th>Item</th><th>Quantity</th><th>Reorder at</th><th>Unit cost</th><th>Status</th><th /></tr></thead><tbody>{(loading || (showArchived && archivedQuery.isLoading)) ? <tr><td colSpan={7}><div className="loading-state">Loading inventory…</div></td></tr> : visibleItems.map((item) => <InventoryRow key={item.id} item={item} canManage={canManage} onArchive={() => { if (window.confirm(`Remove ${item.name} from active inventory? The item must have zero stock. History will be retained.`)) archiveItem.mutate(item); }} onNotice={onNotice} />)}{!loading && visibleItems.length === 0 && <tr><td colSpan={7}><div className="empty-state">{showArchived ? 'No archived inventory items.' : 'No inventory items recorded.'}</div></td></tr>}</tbody></table></div></section>
  </>;
}

function InventoryRow({ item, canManage, onArchive, onNotice }: { item: Inventory; canManage: boolean; onArchive: () => void; onNotice: (message: string) => void }) {
  const client = useQueryClient();
  const [receiving, setReceiving] = useState(false);
  const [quantity, setQuantity] = useState('');
  const [saving, setSaving] = useState(false);
  async function receiveStock(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amount = Number(quantity);
    if (!Number.isInteger(amount) || amount < 1) return;
    setSaving(true);
    try {
      await apiRequest(`/inventory/${item.id}/adjust`, { method: 'POST', body: JSON.stringify({ quantity_delta: amount, reason: 'Stock received' }) });
      await client.invalidateQueries({ queryKey: ['inventory'] });
      setReceiving(false);
      setQuantity('');
      onNotice(`${amount} ${item.unit} added to ${item.name}.`);
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'Stock update failed');
    } finally {
      setSaving(false);
    }
  }
  const archived = Boolean(item.archived_at);
  return <tr><td>{item.sku}</td><td>{item.name}</td><td>{item.quantity_on_hand} {item.unit}</td><td>{item.reorder_level}</td><td>{money(item.unit_cost_ugx)}</td><td><span className={`status-label ${archived ? 'status-label-cancelled' : item.low_stock ? 'status-label-dirty' : 'status-label-available'}`}>{archived ? 'Archived' : item.low_stock ? 'Low stock' : 'In stock'}</span></td><td>{archived ? <span className="muted">Archived</span> : <div className="inventory-row-actions">{receiving ? <form className="receive-stock-form" onSubmit={receiveStock}><input aria-label={`Receive quantity for ${item.name}`} type="number" min="1" step="1" autoFocus value={quantity} onChange={(event) => setQuantity(event.target.value)} /><button className="text-button" type="submit" disabled={saving}>Add</button><button className="text-button" type="button" onClick={() => setReceiving(false)}>Cancel</button></form> : <button className="text-button" onClick={() => setReceiving(true)}>Receive stock</button>}{canManage && <button className="icon-button inventory-remove" aria-label={`Remove ${item.name}`} title={item.quantity_on_hand === 0 ? 'Remove inventory item' : 'Reduce stock to zero before removal'} disabled={item.quantity_on_hand !== 0} onClick={onArchive}><Trash2 size={14} /></button>}</div>}</td></tr>;
}
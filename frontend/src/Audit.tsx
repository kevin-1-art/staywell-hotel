import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronLeft, ChevronRight, RefreshCw, Search } from 'lucide-react';
import { apiRequest } from './api';

type AuditEvent = {
  id: string;
  actor_id: string | null;
  actor_name: string;
  actor_email: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  details: Record<string, unknown>;
  created_at: string;
};
type AuditPage = { items: AuditEvent[]; total: number; limit: number; offset: number };

const actions = [
  'user.created', 'user.updated', 'reservation.created', 'reservation.checked_in',
  'reservation.checked_out', 'reservation.cancelled', 'reservation.no_show',
  'reservation.room_moved', 'checkout.balance_override', 'folio.payment_received',
  'folio.refund_issued', 'maintenance.opened', 'maintenance.closed',
];
export default function Audit() {
  const [search, setSearch] = useState('');
  const [action, setAction] = useState('');
  const [entityType, setEntityType] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState('');
  const params = new URLSearchParams({ limit: '50', offset: String(offset) });
  if (search.trim()) params.set('search', search.trim());
  if (action) params.set('action', action);
  if (entityType) params.set('entity_type', entityType);
  if (fromDate) params.set('from_date', fromDate);
  if (toDate) params.set('to_date', toDate);
  const query = useQuery({
    queryKey: ['audit-log', search, action, entityType, fromDate, toDate, offset],
    queryFn: () => apiRequest<AuditPage>(`/audit-logs?${params.toString()}`),
  });
  const page = query.data;
  const currentStart = page && page.total ? page.offset + 1 : 0;
  const currentEnd = page ? Math.min(page.offset + page.items.length, page.total) : 0;

  function resetFilters() {
    setSearch('');
    setAction('');
    setEntityType('');
    setFromDate('');
    setToDate('');
    setOffset(0);
  }

  return <>
    <div className="page-title-row"><div><span className="eyebrow">ADMINISTRATION</span><h1>Audit log</h1><p className="muted">A chronological record of staff activity and operational changes.</p></div><button className="icon-button" aria-label="Refresh audit log" onClick={() => void query.refetch()}><RefreshCw size={15} /></button></div>
    <section className="audit-filters panel">
      <label className="audit-search"><Search size={14} /><input aria-label="Search audit activity" placeholder="Search actor, action, or entity" value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0); }} /></label>
      <label>Action<select aria-label="Filter by action" value={action} onChange={(event) => { setAction(event.target.value); setOffset(0); }}><option value="">All actions</option>{actions.map((item) => <option key={item} value={item}>{item.replaceAll('.', ' · ').replaceAll('_', ' ')}</option>)}</select></label>
      <label>Entity<select aria-label="Filter by entity" value={entityType} onChange={(event) => { setEntityType(event.target.value); setOffset(0); }}><option value="">All entities</option>{['user', 'reservation', 'folio', 'maintenance_ticket'].map((item) => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}</select></label>
      <label>From<input aria-label="Audit from date" type="date" value={fromDate} onChange={(event) => { setFromDate(event.target.value); setOffset(0); }} /></label>
      <label>To<input aria-label="Audit to date" type="date" value={toDate} onChange={(event) => { setToDate(event.target.value); setOffset(0); }} /></label>
      <button className="text-button" onClick={resetFilters}>Clear filters</button>
    </section>
    <section className="audit-results">
      <div className="audit-results-heading"><span className="eyebrow">ACTIVITY</span><span className="muted">{page ? `${currentStart}–${currentEnd} of ${page.total}` : 'Loading activity'}</span></div>
      <div className="table-wrap"><table><thead><tr><th>When</th><th>Staff member</th><th>Action</th><th>Record</th><th>Details</th></tr></thead><tbody>
        {query.isLoading && <tr><td colSpan={5}><div className="loading-state">Loading audit events…</div></td></tr>}
        {query.isError && <tr><td colSpan={5}><div className="error-banner">Unable to load the audit log.</div></td></tr>}
        {page?.items.map((event) => <AuditRow key={event.id} event={event} expanded={expanded === event.id} onToggle={() => setExpanded(expanded === event.id ? '' : event.id)} />)}
        {!query.isLoading && !query.isError && page?.items.length === 0 && <tr><td colSpan={5}><div className="empty-state">No activity matches these filters.</div></td></tr>}
      </tbody></table></div>
      <div className="audit-pagination"><span className="muted">Page size 50</span><div><button className="icon-button" aria-label="Previous audit page" disabled={!page || offset === 0} onClick={() => setOffset(Math.max(offset - 50, 0))}><ChevronLeft size={16} /></button><button className="icon-button" aria-label="Next audit page" disabled={!page || offset + 50 >= page.total} onClick={() => setOffset(offset + 50)}><ChevronRight size={16} /></button></div></div>
    </section>
  </>;
}

function AuditRow({ event, expanded, onToggle }: { event: AuditEvent; expanded: boolean; onToggle: () => void }) {
  const date = new Date(event.created_at);
  return <>
    <tr className="audit-row" onClick={onToggle}>
      <td><time dateTime={event.created_at}>{new Intl.DateTimeFormat('en-UG', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Kampala' }).format(date)}</time></td>
      <td><strong>{event.actor_name}</strong><small className="staff-email">{event.actor_email ?? 'System event'}</small></td>
      <td><span className="audit-action">{event.action.replaceAll('.', ' · ').replaceAll('_', ' ')}</span></td>
      <td><span className="code-label">{event.entity_type}</span><small className="staff-email">{event.entity_id}</small></td>
      <td><button className="icon-button audit-detail-toggle" aria-label={`${expanded ? 'Hide' : 'Show'} event details`} aria-expanded={expanded}><ChevronDown size={15} /></button></td>
    </tr>
    {expanded && <tr><td colSpan={5}><pre className="audit-details">{JSON.stringify(event.details, null, 2)}</pre></td></tr>}
  </>;
}
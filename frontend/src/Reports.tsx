import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Download, RefreshCw } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from './api';

type ReportItem = Record<string, string | number>;
const today = () => new Date().toISOString().slice(0, 10);
const money = (amount = 0) => new Intl.NumberFormat('en-UG', { style: 'currency', currency: 'UGX', maximumFractionDigits: 0 }).format(amount);

export default function Reports({ onDownload }: { onDownload: (type: string, format: 'csv' | 'pdf') => void }) {
  const to = today();
  const start = new Date();
  start.setDate(start.getDate() - 6);
  const from = start.toISOString().slice(0, 10);
  const occupancy = useQuery({ queryKey: ['occupancy-report', from, to], queryFn: () => apiRequest<{ items: ReportItem[] }>(`/reports/occupancy?from_date=${from}&to_date=${to}`) });
  const revenue = useQuery({ queryKey: ['revenue-report', from, to], queryFn: () => apiRequest<{ items: ReportItem[] }>(`/reports/revenue-source?from_date=${from}&to_date=${to}`) });
  return <>
    <div className="page-title-row"><div><span className="eyebrow">PROPERTY PERFORMANCE</span><h1>Reports</h1><p className="muted">Seven-day operating picture · export any report as CSV or PDF.</p></div></div>
    <div className="report-grid">
      <section className="panel chart-panel"><div className="panel-heading"><div><span className="eyebrow">OCCUPANCY</span><h2>Rooms occupied by day</h2></div><button className="icon-button" aria-label="Refresh reports" onClick={() => void occupancy.refetch()}><RefreshCw size={15} /></button></div><div className="chart-wrap">{occupancy.isLoading ? <div className="loading-state">Loading report…</div> : <ResponsiveContainer width="100%" height="100%"><BarChart data={occupancy.data?.items ?? []}><CartesianGrid vertical={false} stroke="#e4e5dc" /><XAxis dataKey="date" tickFormatter={(value: string) => value.slice(5)} /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="occupied_rooms" name="Occupied rooms" fill="#55755f" radius={[2, 2, 0, 0]} /></BarChart></ResponsiveContainer>}</div></section>
      <section className="panel chart-panel"><div className="panel-heading"><div><span className="eyebrow">REVENUE SOURCE</span><h2>Room revenue by source</h2></div></div><div className="chart-wrap">{revenue.isLoading ? <div className="loading-state">Loading report…</div> : <ResponsiveContainer width="100%" height="100%"><BarChart data={revenue.data?.items ?? []}><CartesianGrid vertical={false} stroke="#e4e5dc" /><XAxis dataKey="group" /><YAxis /><Tooltip formatter={(value) => money(Number(value))} /><Bar dataKey="amount_ugx" name="Revenue" fill="#b98d55" radius={[2, 2, 0, 0]} /></BarChart></ResponsiveContainer>}</div></section>
    </div>
    <section className="panel export-panel"><div><span className="eyebrow">DOWNLOAD DATA</span><h2>Operational reports</h2></div><div className="export-actions">{['occupancy', 'revenue-source', 'revenue-room-type', 'payment-method', 'cancellations', 'staff-performance'].map((type) => <div className="export-item" key={type}><span>{type.replaceAll('-', ' ')}</span><button title={`Download ${type} CSV`} aria-label={`Download ${type} CSV`} onClick={() => onDownload(type, 'csv')}><Download size={14} /><small>CSV</small></button><button title={`Download ${type} PDF`} aria-label={`Download ${type} PDF`} onClick={() => onDownload(type, 'pdf')}><Download size={14} /><small>PDF</small></button></div>)}</div></section>
  </>;
}
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { KeyRound, Plus, Search, ShieldCheck, UserRoundCog } from 'lucide-react';
import { z } from 'zod';
import { apiRequest } from './api';
import type { Role } from './types';

type StaffAccount = { id: string; email: string; full_name: string; role: Role; is_active: boolean; created_at: string; deleted_at: string | null };
type RoleDetail = { key: Role; label: string; description: string; permissions: string[] };
type Page<T> = { items: T[]; total: number; limit: number; offset: number };

const roleValues = ['admin', 'manager', 'front_desk', 'housekeeping', 'accountant'] as const;
const roleLabels: Record<Role, string> = {
  admin: 'Administrator',
  manager: 'Manager',
  front_desk: 'Front Desk',
  housekeeping: 'Housekeeping',
  accountant: 'Accountant',
};
const accountSchema = z.object({
  full_name: z.string().trim().min(2, 'Enter the staff member’s name').max(160),
  email: z.email('Enter a valid email address'),
  role: z.enum(roleValues),
  password: z.string().min(12, 'Use at least 12 characters').max(128)
    .regex(/[a-z]/, 'Add a lower-case letter').regex(/[A-Z]/, 'Add an upper-case letter')
    .regex(/[0-9]/, 'Add a number').regex(/[^A-Za-z0-9]/, 'Add a symbol'),
});
type AccountForm = z.infer<typeof accountSchema>;
const editAccountSchema = z.object({
  full_name: z.string().trim().min(2, 'Enter the staff member’s name').max(160),
  email: z.email('Enter a valid email address'),
  role: z.enum(roleValues),
  password: z.string().optional(),
}).superRefine((value, context) => {
  if (!value.password) return;
  if (value.password.length < 12 || !/[a-z]/.test(value.password) || !/[A-Z]/.test(value.password) || !/[0-9]/.test(value.password) || !/[^A-Za-z0-9]/.test(value.password)) {
    context.addIssue({ code: 'custom', path: ['password'], message: 'Use 12+ characters with mixed case, a number and symbol.' });
  }
});
type EditAccountForm = z.infer<typeof editAccountSchema>;

export default function Staff({ currentUserId, onNotice }: { currentUserId: string; onNotice: (message: string) => void }) {
  const client = useQueryClient();
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<StaffAccount | null>(null);
  const form = useForm<AccountForm>({
    resolver: zodResolver(accountSchema),
    defaultValues: { full_name: '', email: '', role: 'front_desk', password: '' },
  });
  const editForm = useForm<EditAccountForm>({
    resolver: zodResolver(editAccountSchema),
    defaultValues: { full_name: '', email: '', role: 'front_desk', password: '' },
  });
  const usersQuery = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => apiRequest<Page<StaffAccount>>('/admin/users?limit=200'),
  });
  const rolesQuery = useQuery({
    queryKey: ['admin-roles'],
    queryFn: () => apiRequest<RoleDetail[]>('/admin/roles'),
  });
  const createAccount = useMutation({
    mutationFn: (data: AccountForm) => apiRequest<StaffAccount>('/admin/users', { method: 'POST', body: JSON.stringify(data) }),
    onSuccess: (account) => {
      void client.invalidateQueries({ queryKey: ['admin-users'] });
      setShowCreate(false);
      form.reset();
      onNotice(`${account.full_name} has been added as ${roleLabels[account.role]}.`);
    },
    onError: (error: Error) => onNotice(error.message),
  });
  const loadAccount = useMutation({
    mutationFn: (id: string) => apiRequest<StaffAccount>(`/admin/users/${id}`),
    onSuccess: (account) => {
      setEditing(account);
      editForm.reset({ full_name: account.full_name, email: account.email, role: account.role, password: '' });
    },
    onError: (error: Error) => onNotice(error.message),
  });
  const updateAccount = useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: { full_name?: string; email?: string; role?: Role; is_active?: boolean; password?: string } }) =>
      apiRequest<StaffAccount>(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(changes) }),
    onSuccess: (account) => {
      void client.invalidateQueries({ queryKey: ['admin-users'] });
      setEditing(null);
      editForm.reset();
      onNotice(`${account.full_name}’s account has been updated.`);
    },
    onError: (error: Error) => {
      void client.invalidateQueries({ queryKey: ['admin-users'] });
      onNotice(error.message);
    },
  });
  const deleteAccount = useMutation({
    mutationFn: (account: StaffAccount) => apiRequest<StaffAccount>(`/admin/users/${account.id}`, { method: 'DELETE' }),
    onSuccess: (_, account) => {
      void client.invalidateQueries({ queryKey: ['admin-users'] });
      onNotice(`${account.full_name}’s account was deleted and archived.`);
    },
    onError: (error: Error) => onNotice(error.message),
  });
  const users = useMemo(() => (usersQuery.data?.items ?? []).filter((account) => {
    const matchesSearch = `${account.full_name} ${account.email}`.toLowerCase().includes(search.trim().toLowerCase());
    return matchesSearch && (roleFilter === 'all' || account.role === roleFilter);
  }), [usersQuery.data, search, roleFilter]);

  function beginEdit(account: StaffAccount) {
    loadAccount.mutate(account.id);
  }

  return <>
    <div className="page-title-row"><div><span className="eyebrow">ADMINISTRATION</span><h1>Team & access</h1><p className="muted">Create staff accounts and assign system roles.</p></div><button className="primary-button compact" onClick={() => setShowCreate((value) => !value)}><Plus size={16} /> Add staff account</button></div>
    {showCreate && <section className="panel staff-create-panel"><div className="panel-heading"><div><span className="eyebrow">NEW STAFF ACCOUNT</span><h2>Account details</h2></div><KeyRound size={18} /></div><form className="form-grid" onSubmit={form.handleSubmit((values) => createAccount.mutate(values))} noValidate>
      <label>Full name<input autoComplete="name" aria-invalid={!!form.formState.errors.full_name} {...form.register('full_name')} />{form.formState.errors.full_name && <small className="field-error">{form.formState.errors.full_name.message}</small>}</label>
      <label>Work email<input type="email" autoComplete="email" aria-invalid={!!form.formState.errors.email} {...form.register('email')} />{form.formState.errors.email && <small className="field-error">{form.formState.errors.email.message}</small>}</label>
      <label>System role<select {...form.register('role')}>{rolesQuery.data?.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
      <label>Temporary password<input type="password" autoComplete="new-password" aria-invalid={!!form.formState.errors.password} {...form.register('password')} />{form.formState.errors.password && <small className="field-error">{form.formState.errors.password.message}</small>}</label>
      <div className="staff-create-actions"><span><ShieldCheck size={15} /> Password must be 12+ characters with mixed case, a number and symbol.</span><button className="primary-button compact" type="submit" disabled={createAccount.isPending}>{createAccount.isPending ? 'Creating…' : 'Create account'}</button></div>
    </form></section>}
    {editing && <section className="panel staff-edit-panel"><div className="panel-heading"><div><span className="eyebrow">EDIT STAFF ACCOUNT</span><h2>{editing.full_name}</h2></div><button className="icon-button" type="button" aria-label="Close edit account" onClick={() => { setEditing(null); editForm.reset(); }}>×</button></div><form className="form-grid" onSubmit={editForm.handleSubmit((values) => { const { password, ...profile } = values; updateAccount.mutate({ id: editing.id, changes: { ...profile, ...(password ? { password } : {}) } }); })} noValidate>
      <label>Full name<input aria-invalid={!!editForm.formState.errors.full_name} {...editForm.register('full_name')} />{editForm.formState.errors.full_name && <small className="field-error">{editForm.formState.errors.full_name.message}</small>}</label>
      <label>Work email<input type="email" aria-invalid={!!editForm.formState.errors.email} {...editForm.register('email')} />{editForm.formState.errors.email && <small className="field-error">{editForm.formState.errors.email.message}</small>}</label>
      <label>System role<select {...editForm.register('role')}>{rolesQuery.data?.map((role) => <option key={role.key} value={role.key}>{role.label}</option>)}</select></label>
      <label>Reset password (optional)<input type="password" autoComplete="new-password" placeholder="Leave blank to keep current password" aria-invalid={!!editForm.formState.errors.password} {...editForm.register('password')} />{editForm.formState.errors.password && <small className="field-error">{editForm.formState.errors.password.message}</small>}</label>
      <div className="staff-create-actions"><span><ShieldCheck size={15} /> Password changes revoke existing refresh sessions.</span><div className="staff-actions"><button className="secondary-button" type="button" onClick={() => { setEditing(null); editForm.reset(); }}>Cancel</button><button className="primary-button compact" type="submit" disabled={updateAccount.isPending}>{updateAccount.isPending ? 'Saving…' : 'Save changes'}</button></div></div>
    </form></section>}
    <section className="role-catalog"><div className="section-heading"><div><span className="eyebrow">ROLE PERMISSIONS</span><h2>Five clear access levels</h2></div><span className="muted">Enforced by the API</span></div><div className="role-card-grid">{rolesQuery.isLoading ? <div className="loading-state">Loading role permissions…</div> : rolesQuery.data?.map((role) => <article className="role-card" key={role.key}><span className={`role-symbol role-symbol-${role.key}`}><UserRoundCog size={17} /></span><h3>{role.label}</h3><p>{role.description}</p><ul>{role.permissions.map((permission) => <li key={permission}>{permission}</li>)}</ul></article>)}</div></section>
    <section className="staff-directory"><div className="section-heading"><div><span className="eyebrow">STAFF DIRECTORY</span><h2>{usersQuery.data?.total ?? 0} accounts</h2></div><div className="staff-filters"><label className="staff-search"><Search size={14} /><input aria-label="Search staff" placeholder="Name or email" value={search} onChange={(event) => setSearch(event.target.value)} /></label><select aria-label="Filter by role" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}><option value="all">All roles</option>{rolesQuery.data?.map((role) => <option key={role.key} value={role.key}>{role.label}</option>)}</select></div></div><div className="table-wrap"><table><thead><tr><th>Staff member</th><th>Role</th><th>Account</th><th>Added</th><th>Access and lifecycle</th></tr></thead><tbody>{usersQuery.isLoading ? <tr><td colSpan={5}><div className="loading-state">Loading staff…</div></td></tr> : users.map((account) => <tr key={account.id}><td><strong>{account.full_name}</strong><small className="staff-email">{account.email}</small></td><td><span className={`role-chip role-chip-${account.role}`}>{roleLabels[account.role]}</span></td><td><span className={`status-label ${account.deleted_at ? 'status-label-cancelled' : account.is_active ? 'status-label-available' : 'status-label-cleaning'}`}>{account.deleted_at ? 'Deleted' : account.is_active ? 'Active' : 'Inactive'}</span></td><td>{new Intl.DateTimeFormat('en-UG', { dateStyle: 'medium' }).format(new Date(account.created_at))}</td><td><div className="staff-actions">{!account.deleted_at && <button className="text-button" disabled={loadAccount.isPending} onClick={() => beginEdit(account)}>{loadAccount.isPending ? 'Loading…' : 'Edit'}</button>}<select aria-label={`Role for ${account.full_name}`} value={account.role} disabled={Boolean(account.deleted_at)} onChange={(event) => updateAccount.mutate({ id: account.id, changes: { role: event.target.value as Role } })}><option value={account.role}>{roleLabels[account.role]}</option>{rolesQuery.data?.filter((role) => role.key !== account.role).map((role) => <option key={role.key} value={role.key}>{role.label}</option>)}</select>{account.deleted_at ? <span className="muted">Archived</span> : account.id === currentUserId ? <span className="muted">Current account</span> : <><button className="text-button" onClick={() => { const action = account.is_active ? 'Deactivate' : 'Reactivate'; if (window.confirm(`${action} ${account.full_name}’s account?`)) updateAccount.mutate({ id: account.id, changes: { is_active: !account.is_active } }); }}>{account.is_active ? 'Deactivate' : 'Reactivate'}</button><button className="text-button staff-delete" onClick={() => { if (window.confirm(`Delete ${account.full_name}’s account? They will lose access, and their audit/history records will be retained.`)) deleteAccount.mutate(account); }}>Delete</button></>}</div></td></tr>)}{!usersQuery.isLoading && users.length === 0 && <tr><td colSpan={5}><div className="empty-state">No staff accounts match these filters.</div></td></tr>}</tbody></table></div></section>
  </>;
}
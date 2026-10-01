import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowRight, Building2, LoaderCircle, ShieldCheck } from 'lucide-react';
import { z } from 'zod';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { health, login, logout, refreshSession, setAccessToken } from './api';
import Operations, { type Section } from './Operations';
import type { Session } from './types';

const credentialsSchema = z.object({
  email: z.email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
});
type Credentials = z.infer<typeof credentialsSchema>;

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [authError, setAuthError] = useState('');
  const [section, setSection] = useState<Section>('overview');
  const { register, handleSubmit, formState: { errors } } = useForm<Credentials>({
    resolver: zodResolver(credentialsSchema),
  });
  const statusQuery = useQuery({ queryKey: ['health'], queryFn: health, refetchInterval: 60_000 });
  const loginMutation = useMutation({
    mutationFn: (values: Credentials) => login(values.email, values.password),
    onSuccess: (value) => { setAccessToken(value.access_token); setSession(value); setAuthError(''); },
    onError: (error: Error) => setAuthError(error.message),
  });

  useEffect(() => {
    refreshSession().then((value) => { setAccessToken(value.access_token); setSession(value); }).catch(() => { setAccessToken(''); setSession(null); }).finally(() => setRestoring(false));
  }, []);

  async function signOut() {
    await logout().catch(() => undefined);
    setAccessToken('');
    setSession(null);
  }

  if (restoring) {
    return <main className="loading-screen" aria-label="Restoring session"><LoaderCircle className="spin" size={24} /></main>;
  }

  if (!session) {
    return (
      <main className="auth-layout">
        <section className="auth-story" aria-label="Staywell Hotel">
          <div className="story-top"><span className="brand-mark"><Building2 size={21} /></span><span>STAYWELL <small>HOTEL OPERATIONS</small></span></div>
          <div className="story-copy">
            <span className="eyebrow">THE ART OF A GOOD STAY</span>
            <h1>Thoughtful stays.<br /><em>Effortless days.</em></h1>
            <p>One calm place to run the details that make a hotel feel like home.</p>
          </div>
          <div className="story-foot"><span>OPERATIONS CONSOLE</span><span>UGANDA · EAST AFRICA</span></div>
        </section>
        <section className="auth-panel">
          <div className="auth-form-wrap">
            <div className="mobile-brand"><span className="brand-mark"><Building2 size={20} /></span> STAYWELL</div>
            <span className="eyebrow">WELCOME BACK</span>
            <h2>Sign in to your desk</h2>
            <p className="muted">Use your staff account to continue.</p>
            <form onSubmit={handleSubmit((values) => loginMutation.mutate(values))} noValidate>
              <label htmlFor="email">Work email</label>
              <input id="email" autoComplete="username" type="email" placeholder="you@staywell.ug" aria-invalid={!!errors.email} {...register('email')} />
              {errors.email && <span className="field-error">{errors.email.message}</span>}
              <label htmlFor="password">Password</label>
              <input id="password" autoComplete="current-password" type="password" placeholder="Your password" aria-invalid={!!errors.password} {...register('password')} />
              {errors.password && <span className="field-error">{errors.password.message}</span>}
              {authError && <div className="form-error" role="alert">{authError}</div>}
              <button className="primary-button" type="submit" disabled={loginMutation.isPending}>
                {loginMutation.isPending ? <LoaderCircle className="spin" size={17} /> : <>Enter workspace <ArrowRight size={17} /></>}
              </button>
            </form>
            <div className="secure-note"><ShieldCheck size={15} /> Protected staff access</div>
          </div>
          <footer className="auth-footer"><span>© 2026 Staywell Hotel</span><span className={`health-indicator ${statusQuery.data ? 'online' : ''}`}><i /> {statusQuery.data ? 'Systems operational' : 'Connecting to system'}</span></footer>
        </section>
      </main>
    );
  }

  return <Operations role={session.user.role} section={section} setSection={setSection} userId={session.user.id} userName={session.user.full_name} onSignOut={signOut} />;
}
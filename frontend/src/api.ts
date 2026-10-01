import type { Session } from './types';

const apiOrigin = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');
const apiRoot = `${apiOrigin}/api/v1`;
let accessToken = '';

export function setAccessToken(value: string): void {
  accessToken = value;
}

export async function login(email: string, password: string): Promise<Session> {
  return request<Session>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export async function refreshSession(): Promise<Session> {
  return request<Session>('/auth/refresh', { method: 'POST' });
}

export async function logout(): Promise<void> {
  await request<void>('/auth/logout', { method: 'POST' });
}

export async function health(): Promise<{ status: string; database: string }> {
  const response = await fetch(`${apiOrigin}/health`, { credentials: 'include' });
  if (!response.ok) throw new Error('API health check failed');
  return response.json() as Promise<{ status: string; database: string }>;
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  return request<T>(path, init);
}

export async function apiDownload(path: string): Promise<Blob> {
  const response = await fetch(`${apiRoot}${path}`, {
    credentials: 'include',
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? 'Download failed');
  }
  return response.blob();
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${apiRoot}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? 'Request failed');
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
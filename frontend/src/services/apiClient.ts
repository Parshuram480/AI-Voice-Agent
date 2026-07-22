export const API_BASE = 'http://localhost:8000';

export async function request<T = any>(url: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('auth_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const defaults: RequestInit = {
    credentials: 'include',
    ...options,
    headers,
  };

  const response = await fetch(url, defaults);
  const contentType = response.headers.get('content-type');
  
  let data: any = null;
  if (contentType && contentType.includes('application/json')) {
    data = await response.json();
  }

  if (!response.ok) {
    const errorMsg = data?.detail || data?.message || response.statusText || `HTTP error ${response.status}`;
    throw new Error(errorMsg);
  }

  return data as T;
}

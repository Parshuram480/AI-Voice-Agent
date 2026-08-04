import { request, API_BASE } from './apiClient';

export const authService = {
  async checkAuth() {
    return request(`${API_BASE}/api/auth/me`);
  },

  async login(payload: any) {
    const res = await request(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (res.token) {
      localStorage.setItem('auth_token', String(res.token));
    }
    return res;
  },

  async register(payload: any) {
    const res = await request(`${API_BASE}/api/auth/register`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (res.token || res.client_id) {
      localStorage.setItem('auth_token', String(res.token || res.client_id));
    }
    return res;
  },

  async logout() {
    localStorage.removeItem('auth_token');
    return request(`${API_BASE}/api/auth/logout`, {
      method: 'POST',
    });
  },

  async sendOtp(email: string, clientName: string) {
    return request(`${API_BASE}/api/auth/send-otp`, {
      method: 'POST',
      body: JSON.stringify({ email, client_name: clientName }),
    });
  },

  async verifyOtp(email: string, otp: string) {
    return request(`${API_BASE}/api/auth/verify-otp`, {
      method: 'POST',
      body: JSON.stringify({ email, otp }),
    });
  },

  async updateProfile(payload: {
    company_name: string;
    client_name: string;
    email: string;
    phone?: string;
    domain_id: number;
  }) {
    return request(`${API_BASE}/api/auth/profile`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },
};

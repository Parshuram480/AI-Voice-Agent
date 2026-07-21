import { request, API_BASE } from './apiClient';

export const authService = {
  async checkAuth() {
    return request(`${API_BASE}/api/auth/me`);
  },

  async login(payload: any) {
    return request(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async register(payload: any) {
    return request(`${API_BASE}/api/auth/register`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async logout() {
    return request(`${API_BASE}/api/auth/logout`, {
      method: 'POST',
    });
  },
};

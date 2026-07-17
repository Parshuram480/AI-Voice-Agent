import { request, API_BASE } from './apiClient';

export const domainService = {
  async getDomains() {
    return request<any[]>(`${API_BASE}/api/domains`);
  },
};

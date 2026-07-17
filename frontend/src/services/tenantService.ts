import { request, API_BASE } from './apiClient';

export const tenantService = {
  async testConnection(config: any) {
    return request(`${API_BASE}/api/tenant/test-connection`, {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },

  async saveDbConfig(config: any) {
    return request(`${API_BASE}/api/tenant/db-config`, {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },
};

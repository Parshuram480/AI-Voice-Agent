import { request, API_BASE } from './apiClient';

export interface DbConfig {
  db_type: string;
  server_name?: string;
  port?: number | '';
  db_name: string;
  username?: string;
  password?: string;
  schema_name?: string;
  enable_ssl?: boolean;
  trust_server_certificate?: boolean;
  connection_timeout?: number;
}

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

  async uploadSqliteDb(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/tenant/upload-sqlite`, {
      method: 'POST',
      body: formData,
    });
    return res.json();
  },

  async introspectDb(config: any) {
    return request(`${API_BASE}/api/tenant/db-config/introspect`, {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },

  async generateRules(payload: {
    db_config: any;
    customer_table: string;
    verification_fields: string[];
    data_table: string;
    data_fields: string[];
    schema_data: Record<string, string[]>;
  }) {
    return request(`${API_BASE}/api/tenant/db-config/generate-rules`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async testQuery(payload: {
    db_config: any;
    verification_query: string;
    data_query: string;
    test_inputs: string[];
  }) {
    return request(`${API_BASE}/api/tenant/db-config/test-query`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async saveRules(payload: {
    db_config: any;
    domain_id: number;
    verification_query: string;
    data_query: string;
    client_id?: number;
    ui_config_metadata?: any;
  }) {
    return request(`${API_BASE}/api/tenant/db-config/save-rules`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};

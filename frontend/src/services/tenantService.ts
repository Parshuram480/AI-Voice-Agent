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

  async saveRules(payload: {
    db_config?: DbConfig;
    domain_id: number;
    identity: {
      table: string;
      name_column: string;
      verification_column: string;
      display_columns: string[];
    };
    selected_tables: Record<string, string[]>;
    client_id?: number;
    ui_config_metadata?: any;
  }) {
    return request(`${API_BASE}/api/tenant/db-config/save-rules`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};

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

export interface OutreachConfigRequest {
  db_config: DbConfig;
  campaign_type: string;
  product_table: string;
  selected_columns: string[];
  company_name: string;
  closing_goal: string;
  ui_config_metadata?: Record<string, any>;
}

export interface OutreachCallRequest {
  phone_number: string;
  customer_name: string;
  language?: string;
}

export const outreachService = {
  generateDummyDb: async (campaignType: string) => {
    return await request(`${API_BASE}/api/outreach/generate-dummy`, {
      method: 'POST',
      body: JSON.stringify({ campaign_type: campaignType })
    });
  },

  saveConfig: async (data: OutreachConfigRequest) => {
    return await request(`${API_BASE}/api/outreach/save-config`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  },
  
  getConfig: async () => {
    return await request(`${API_BASE}/api/outreach/config`, {
      method: 'GET'
    });
  },

  triggerCall: async (data: OutreachCallRequest) => {
    return await request(`${API_BASE}/api/outreach/call`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }
};

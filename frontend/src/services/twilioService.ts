import { request, API_BASE } from './apiClient';

export const twilioService = {
  async getCallStatus(sid: string) {
    return request(`${API_BASE}/api/twilio/call/${sid}`);
  },

  async dialCall(payload: { phone_number: string; client_id: number }) {
    return request(`${API_BASE}/api/twilio/call`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async endCall(sid: string) {
    return request(`${API_BASE}/api/twilio/call/${sid}/end`, {
      method: 'POST',
    });
  },
};

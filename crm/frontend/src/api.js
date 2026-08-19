/**
 * RankBuilder CRM — API Client (with JWT auth)
 */

const BASE = '/api';

function getToken() {
  return localStorage.getItem('crm_token');
}

async function request(method, path, body = null, authenticated = false) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (authenticated) {
    const token = getToken();
    if (token) opts.headers['Authorization'] = `Bearer ${token}`;
  }
  if (body) {
    if (body instanceof URLSearchParams) {
      opts.body = body;
      opts.headers['Content-Type'] = 'application/x-www-form-urlencoded';
    } else {
      opts.body = JSON.stringify(body);
      opts.headers['Content-Type'] = 'application/json';
    }
  }

  const res = await fetch(`${BASE}${path}`, opts);

  if (res.status === 401) {
    localStorage.removeItem('crm_token');
    localStorage.removeItem('crm_user');
    window.dispatchEvent(new Event('auth:logout'));
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    const raw = await res.text();
    let msg = `HTTP ${res.status}`;
    try {
      const data = JSON.parse(raw);
      if (Array.isArray(data?.detail)) {
        msg = data.detail.map(d => typeof d === 'string' ? d : d.msg || JSON.stringify(d)).join(', ');
      } else if (typeof data?.detail === 'string') {
        msg = data.detail;
      } else if (data?.message) {
        msg = data.message;
      }
    } catch { /* use default msg */ }
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Auth ───────────────────────────────────────────────────────────────────────

export const auth = {
  login: (email, password) =>
    request('POST', '/auth/login', new URLSearchParams({ username: email, password })),

  register: (data) => request('POST', '/auth/register', data),

  me: () => request('GET', '/auth/me', null, true),

  getToken,
};

// ── Clients ────────────────────────────────────────────────────────────────────

export const api = {
  // Clients
  createClient: (data) => request('POST', '/clients', data, true),
  listClients: () => request('GET', '/clients', null, true),
  getClient: (id) => request('GET', `/clients/${id}`, null, true),
  onboardClient: (data) => request('POST', '/clients/onboard', data, true),

  // Leads
  createLead: (data) => request('POST', '/leads', data, true),
  listLeads: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/leads${qs ? '?' + qs : ''}`, null, true);
  },
  exportLeads: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/leads/export${qs ? '?' + qs : ''}`, null, true);
  },
  getLead: (id) => request('GET', `/leads/${id}`, null, true),
  getLeadHistory: (id) => request('GET', `/leads/${id}/history`, null, true),
  updateLead: (id, data) => request('PATCH', `/leads/${id}`, data, true),
  deleteLead: (id) => request('DELETE', `/leads/${id}`, null, true),
  assignLead: (id, data) => request('POST', `/leads/${id}/assign`, data, true),
  logFollowUp: (id, data) => request('POST', `/leads/${id}/follow-up`, data, true),

  // Documents (attachments)
  listDocuments: (id) => request('GET', `/leads/${id}/documents`, null, true),
  uploadDocument: (id, file, category) => {
    const fd = new FormData();
    fd.append('file', file);
    if (category) fd.append('category', category);
    const token = getToken();
    return fetch(`${BASE}/leads/${id}/documents${category ? '?category=' + category : ''}`, {
      method: 'POST',
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      body: fd,
    }).then(async res => {
      if (!res.ok) {
        const raw = await res.text();
        throw new Error(`Upload failed: ${res.status} ${raw.slice(0, 120)}`);
      }
      return res.json();
    });
  },
  downloadDocumentUrl: (id, docId) => `/api/leads/${id}/documents/${docId}/download`,
  deleteDocument: (id, docId) => request('DELETE', `/leads/${id}/documents/${docId}`, null, true),

  // Users
  createUser: (data) => request('POST', '/auth/users', data, true),
  listUsers: () => request('GET', '/auth/users', null, true),
  deleteUser: (id) => request('DELETE', `/auth/users/${id}`, null, true),
  changePassword: (currentPassword, newPassword) =>
    request('POST', '/auth/change-password', { current_password: currentPassword, new_password: newPassword }, true),

  // Dashboard
  dashboardSummary: (clientId, days = 30) =>
    request('GET', `/dashboard/summary?client_id=${clientId}&days=${days}`, null, true),

  // Campaigns
  listCampaigns: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/campaigns${qs ? '?' + qs : ''}`, null, true);
  },
  getCampaign: (id) => request('GET', `/campaigns/${id}`, null, true),
  createCampaign: (data) => request('POST', '/campaigns', data, true),
  updateCampaign: (id, data) => request('PATCH', `/campaigns/${id}`, data, true),
  deleteCampaign: (id) => request('DELETE', `/campaigns/${id}`, null, true),
};

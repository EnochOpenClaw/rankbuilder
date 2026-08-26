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
  archiveLead: (id) => request('POST', `/leads/${id}/archive`, null, true),
  restoreLead: (id) => request('POST', `/leads/${id}/restore`, null, true),
  deleteLead: (id) => request('DELETE', `/leads/${id}`, null, true),
  assignLead: (id, data) => request('POST', `/leads/${id}/assign`, data, true),
  logFollowUp: (id, data) => request('POST', `/leads/${id}/follow-up`, data, true),
  listActivities: (id) => request('GET', `/leads/${id}/activities`, null, true),

  // Sources (admin-managed)
  listSources: () => request('GET', '/sources', null, true),
  listAllSources: () => request('GET', '/sources/all', null, true),
  createSource: (data) => request('POST', '/sources', data, true),
  updateSource: (id, data) => request('PATCH', `/sources/${id}`, data, true),
  deleteSource: (id) => request('DELETE', `/sources/${id}`, null, true),

  // Scoring rules
  listScoringRules: () => request('GET', '/scoring/rules', null, true),
  createScoringRule: (data) => request('POST', '/scoring/rules', data, true),
  updateScoringRule: (id, data) => request('PATCH', `/scoring/rules/${id}`, data, true),
  deleteScoringRule: (id) => request('DELETE', `/scoring/rules/${id}`, null, true),
  getScoringTiers: () => request('GET', '/scoring/tiers', null, true),

  // Reports
  agentSalesReport: (clientId, df, dt) => request('GET', `/reports/agent?client_id=${clientId || ''}&date_from=${df || ''}&date_to=${dt || ''}`, null, true),
  pipelineReport: (clientId, df, dt) => request('GET', `/reports/pipeline?client_id=${clientId || ''}&date_from=${df || ''}&date_to=${dt || ''}`, null, true),
  funnelReport: (clientId, df, dt) => request('GET', `/reports/funnel?client_id=${clientId || ''}&date_from=${df || ''}&date_to=${dt || ''}`, null, true),
  sourceRoiReport: (clientId, df, dt) => request('GET', `/reports/source-roi?client_id=${clientId || ''}&date_from=${df || ''}&date_to=${dt || ''}`, null, true),
  responseTimeReport: (clientId, df, dt) => request('GET', `/reports/response-time?client_id=${clientId || ''}&date_from=${df || ''}&date_to=${dt || ''}`, null, true),
  activityReport: (clientId, df, dt) => request('GET', `/reports/activity?client_id=${clientId || ''}&date_from=${df || ''}&date_to=${dt || ''}`, null, true),
  funnelTrendReport: (clientId, df, dt, bucket) => request('GET', `/reports/funnel-trend?client_id=${clientId || ''}&date_from=${df || ''}&date_to=${dt || ''}&bucket=${bucket || 'week'}`, null, true),
  overdueReport: (clientId) => request('GET', `/reports/overdue?client_id=${clientId || ''}`, null, true),

  // AI
  draftReply: (leadId) => request('POST', '/ai/draft-reply', { lead_id: leadId }, true),

  // Documents (attachments)
  listDocuments: (id) => request('GET', `/leads/${id}/documents`, null, true),
  uploadDocument: (id, file, category) => {
    const fd = new FormData();
    fd.append('file', file);
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
  downloadDocument: async (id, docId) => {
    // Fetch the file WITH the auth header (a plain <a href> new-tab navigation
    // does NOT send the Authorization header, so the backend rejects it).
    const token = getToken();
    const res = await fetch(`${BASE}/leads/${id}/documents/${docId}/download`, {
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const raw = await res.text();
      throw new Error(`Download failed: ${res.status} ${raw.slice(0, 120)}`);
    }
    return res.blob();
  },
  deleteDocument: (id, docId) => request('DELETE', `/leads/${id}/documents/${docId}`, null, true),

  // Reminders (scheduled notifications)
  createReminder: (id, data) => request('POST', `/leads/${id}/reminders`, data, true),
  listReminders: (id) => request('GET', `/leads/${id}/reminders`, null, true),
  dismissReminder: (id, rid) => request('POST', `/leads/${id}/reminders/${rid}/dismiss`, null, true),

  // Email / notification log (per-lead audit trail)
  listEmails: (id) => request('GET', `/leads/${id}/emails`, null, true),

  // Users
  createUser: (data) => request('POST', '/auth/users', data, true),
  listUsers: () => request('GET', '/auth/users', null, true),
  deleteUser: (id) => request('DELETE', `/auth/users/${id}`, null, true),
  resetPassword: (id, newPassword) =>
    request('POST', `/auth/users/${id}/reset-password`, { new_password: newPassword }, true),
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
  logDailyTally: (id, data) => request('POST', `/campaigns/${id}/daily-logs`, data, true),
  roadsideComparison: (clientId) => request('GET', `/campaigns/roadside-comparison?client_id=${clientId || ''}`, null, true),
};

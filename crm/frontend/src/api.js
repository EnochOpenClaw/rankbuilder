/**
 * RankBuilder CRM — API Client
 */

const BASE = '/api';

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Clients ────────────────────────────────────────────────────────────────────

export const api = {
  // Clients
  createClient: (data) => request('POST', '/clients', data),
  listClients: () => request('GET', '/clients'),
  getClient: (id) => request('GET', `/clients/${id}`),

  // Leads
  createLead: (data) => request('POST', '/leads', data),
  listLeads: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/leads${qs ? '?' + qs : ''}`);
  },
  getLead: (id) => request('GET', `/leads/${id}`),
  updateLead: (id, data) => request('PATCH', `/leads/${id}`, data),
  deleteLead: (id) => request('DELETE', `/leads/${id}`),

  // Dashboard
  dashboardSummary: (clientId, days = 30) =>
    request('GET', `/dashboard/summary?client_id=${clientId}&days=${days}`),
};

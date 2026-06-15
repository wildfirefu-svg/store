const jsonHeaders = { 'Content-Type': 'application/json' };

async function request(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`${response.status} ${text}`);
    }
    return response.json();
}

export async function listClients(params = {}) {
    const query = new URLSearchParams();
    if (params.search) query.set('search', params.search);
    if (params.tag) query.set('tag', params.tag);
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return request(`/api/clients${suffix}`);
}

export async function createClient(data) {
    return request('/api/clients', { method: 'POST', headers: jsonHeaders, body: JSON.stringify(data) });
}

export async function getClient(id) {
    return request(`/api/clients/${encodeURIComponent(id)}`);
}

export async function updateClient(id, data) {
    return request(`/api/clients/${encodeURIComponent(id)}`, { method: 'PUT', headers: jsonHeaders, body: JSON.stringify(data) });
}

export async function deleteClient(id) {
    return request(`/api/clients/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function linkClientChart(clientId, chartId) {
    return request(`/api/clients/${encodeURIComponent(clientId)}/charts/${encodeURIComponent(chartId)}`, { method: 'POST' });
}

export async function listClientCharts(clientId) {
    return request(`/api/clients/${encodeURIComponent(clientId)}/charts`);
}

export async function listClientAnalyses(id) {
    return request(`/api/clients/${encodeURIComponent(id)}/analyses`);
}

export async function submitFeedback(analysisId, data) {
    return request(`/api/analyses/${encodeURIComponent(analysisId)}/feedback`, { method: 'POST', headers: jsonHeaders, body: JSON.stringify(data) });
}

export async function getFeedbackStats() {
    return request('/api/feedback/stats');
}

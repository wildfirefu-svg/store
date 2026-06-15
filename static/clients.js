import { createClient, deleteClient, getClient, listClientAnalyses, listClientCharts, listClients, linkClientChart } from './js/client-api.js';
import { renderTimeline } from './js/timeline.js';

const state = { clients: [], currentClient: null };
const $ = (id) => document.getElementById(id);

async function refreshClients() {
    const search = $('search').value.trim();
    const data = await listClients({ search });
    state.clients = data.clients || [];
    renderClientList();
}

function renderClientList() {
    const list = $('client-list');
    list.innerHTML = '';
    if (state.clients.length === 0) {
        list.innerHTML = '<div class="empty">暂无客户</div>';
        return;
    }
    state.clients.forEach((client) => {
        const item = document.createElement('button');
        item.className = 'client-item';
        item.innerHTML = `<strong>${escapeHtml(client.name)}</strong><span>${escapeHtml((client.tags || []).join('、'))}</span>`;
        item.addEventListener('click', () => openClient(client.id));
        list.appendChild(item);
    });
}

async function openClient(id) {
    state.currentClient = await getClient(id);
    $('detail-title').textContent = state.currentClient.name;
    $('detail-meta').textContent = [state.currentClient.gender, state.currentClient.birth_year, state.currentClient.birth_location].filter(Boolean).join(' · ');
    $('detail-notes').textContent = state.currentClient.notes || '暂无备注';
    await refreshClientCharts();
    await refreshTimeline();
}

async function refreshClientCharts() {
    if (!state.currentClient) return;
    const data = await listClientCharts(state.currentClient.id);
    const box = $('chart-list');
    const charts = data.charts || [];
    box.innerHTML = charts.length ? charts.map((chart) => `<div>${escapeHtml(chart.name || chart.chart_id)} · ${escapeHtml(chart.chart_id)}</div>`).join('') : '<div class="empty">暂无关联命盘</div>';
}

async function refreshTimeline() {
    if (!state.currentClient) return;
    const data = await listClientAnalyses(state.currentClient.id);
    renderTimeline($('timeline'), data.analyses || [], refreshTimeline);
}

async function handleCreateClient(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = {
        name: form.name.value.trim(),
        gender: form.gender.value || null,
        birth_year: numberOrNull(form.birth_year.value),
        birth_month: numberOrNull(form.birth_month.value),
        birth_day: numberOrNull(form.birth_day.value),
        birth_hour: numberOrNull(form.birth_hour.value),
        birth_minute: numberOrNull(form.birth_minute.value) || 0,
        birth_location: form.birth_location.value.trim() || 'Beijing',
        tags: form.tags.value.split(',').map((s) => s.trim()).filter(Boolean),
        notes: form.notes.value.trim(),
    };
    if (!data.name) return;
    const client = await createClient(data);
    form.reset();
    await refreshClients();
    await openClient(client.id);
}

async function handleLinkChart(event) {
    event.preventDefault();
    if (!state.currentClient) return;
    const chartId = $('chart-id').value.trim();
    if (!chartId) return;
    await linkClientChart(state.currentClient.id, chartId);
    $('chart-id').value = '';
    await refreshClientCharts();
}

async function handleDeleteClient() {
    if (!state.currentClient) return;
    if (!confirm(`确定删除客户 ${state.currentClient.name}？`)) return;
    await deleteClient(state.currentClient.id);
    state.currentClient = null;
    $('detail-title').textContent = '未选择客户';
    $('detail-meta').textContent = '';
    $('detail-notes').textContent = '';
    $('chart-list').innerHTML = '';
    $('timeline').innerHTML = '';
    await refreshClients();
}

function numberOrNull(value) {
    const n = Number(value);
    return Number.isFinite(n) && value !== '' ? n : null;
}

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }[ch]));
}

$('search').addEventListener('input', () => refreshClients().catch(console.error));
$('client-form').addEventListener('submit', (event) => handleCreateClient(event).catch(console.error));
$('link-chart-form').addEventListener('submit', (event) => handleLinkChart(event).catch(console.error));
$('delete-client').addEventListener('click', () => handleDeleteClient().catch(console.error));
refreshClients().catch(console.error);

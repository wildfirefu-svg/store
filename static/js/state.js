// ================================================================
// 玄机子 Frontend — 状态管理
// MingzhuManager / ChatHistory / CorrectionManager / PersistenceSync
// ================================================================

import { API } from './api.js';
import { _escHtml } from './markdown.js';

// ── MingzhuManager ──
export const MingzhuManager = {
    STORAGE_KEY: 'bazi_mingzhu_list',
    getAll() { try { return JSON.parse(localStorage.getItem(this.STORAGE_KEY)) || []; } catch { return []; } },
    save(mz) {
        const list = this.getAll(); const idx = list.findIndex(m => m.chart_id === mz.chart_id);
        if (idx >= 0) list[idx] = mz; else list.push(mz);
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(list)); return list;
    },
    remove(chartId) {
        const list = this.getAll().filter(m => m.chart_id !== chartId);
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(list));
        if (this.getCurrent()?.chart_id === chartId) localStorage.removeItem('bazi_current_mingzhu');
        return list;
    },
    getCurrent() { const id = localStorage.getItem('bazi_current_mingzhu'); return id ? this.getAll().find(m => m.chart_id === id) || null : null; },
    setCurrent(id) { localStorage.setItem('bazi_current_mingzhu', id); }
};

// ── PersistenceSync (defined before ChatHistory since ChatHistory depends on it) ──
export const PersistenceSync = {
    async loadFromServer() {
        try {
            var resp = await fetch(API + '/charts');
            if (!resp.ok) return;
            var charts = await resp.json();
            charts = Array.isArray(charts) ? charts : [];
            var serverIds = new Set(charts.map(function(c) { return c.chart_id; }));
            var local = MingzhuManager.getAll();
            // Drop any local mingzhu that no longer exists on the server.
            var pruned = local.filter(function(m) { return serverIds.has(m.chart_id); });
            if (pruned.length !== local.length) {
                localStorage.setItem('bazi_mingzhu_list', JSON.stringify(pruned));
                local = pruned;
            }
            // If a previously selected mingzhu was pruned, clear the pointer.
            var currentId = localStorage.getItem('bazi_current_mingzhu');
            if (currentId && !serverIds.has(currentId)) {
                localStorage.removeItem('bazi_current_mingzhu');
            }
            // Pull any server mingzhu that the local cache is missing.
            for (var i = 0; i < charts.length; i++) {
                var c = charts[i];
                if (!local.find(function(m) { return m.chart_id === c.chart_id; })) {
                    try {
                        var fullResp = await fetch(API + '/charts/' + c.chart_id + '/data');
                        if (fullResp.ok) {
                            var full = await fullResp.json();
                            var bi = full.birth_info || {};
                            local.push({
                                chart_id: c.chart_id,
                                name: c.name || '命主',
                                birth: (bi.year||'')+'-'+String(bi.month||'')+'-'+String(bi.day||'')+' '+String(bi.hour||'')+':'+String(bi.minute||'0'),
                                gender: bi.gender || 'male',
                                day_master: (full.chart_data || {}).day_master ? full.chart_data.day_master.gan + (full.chart_data.day_master.wuxing||'') : '',
                                _chart: full.chart_data || {}
                            });
                        }
                    } catch(e) { /* skip failed loads */ }
                }
            }
            localStorage.setItem('bazi_mingzhu_list', JSON.stringify(local));
        } catch(e) { console.warn('同步失败，数据暂存本地，将在下次连接时重试', e); }
    },

    async saveChartToServer(chartId, name, birthInfo, chartData) {
        try {
            await fetch(API + '/charts/save', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({chart_id: chartId, name: name, birth_info: birthInfo, chart_data: chartData})
            });
        } catch(e) { console.warn('同步失败，数据暂存本地，将在下次连接时重试', e); }
    },

    async deleteChartFromServer(chartId) {
        try { await fetch(API + '/charts/' + chartId, {method: 'DELETE'}); } catch(e) { console.warn('同步失败，数据暂存本地，将在下次连接时重试', e); }
    },

    async saveChatMessage(chartId, role, text, tool) {
        try {
            await fetch(API + '/charts/' + chartId + '/history', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({role: role, text: text, tool: tool || null})
            });
        } catch(e) { console.warn('同步失败，数据暂存本地，将在下次连接时重试', e); }
    },

    async loadChatHistory(chartId) {
        try {
            var resp = await fetch(API + '/charts/' + chartId + '/history');
            if (!resp.ok) return null;
            return await resp.json();
        } catch(e) { return null; }
    },

    async saveReport(chartId, tabId, content) {
        try {
            await fetch(API + '/charts/reports/save', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({chart_id: chartId, tab_id: tabId, content: content})
            });
        } catch(e) { console.warn('同步失败，数据暂存本地，将在下次连接时重试', e); }
    },

    async loadReports(chartId) {
        try {
            var resp = await fetch(API + '/charts/' + chartId + '/reports');
            if (!resp.ok) return {};
            return await resp.json();
        } catch(e) { return {}; }
    }
};

// ── ChatHistory ──
export const ChatHistory = {
    PREFIX: 'bazi_chat_',
    MAX_MSGS: 200,
    _restoring: false,

    _key(chartId) { return this.PREFIX + chartId; },

    load(chartId) {
        if (!chartId) return [];
        try { return JSON.parse(localStorage.getItem(this._key(chartId))) || []; }
        catch { return []; }
    },

    save(chartId, messages) {
        if (!chartId) return;
        var trimmed = messages.slice(-this.MAX_MSGS);
        try { localStorage.setItem(this._key(chartId), JSON.stringify(trimmed)); }
        catch { /* storage full */ }
    },

    append(chartId, role, text, tool) {
        if (!chartId || this._restoring) return;
        var msgs = this.load(chartId);
        msgs.push({role: role, text: text, tool: tool || null});
        this.save(chartId, msgs);
        PersistenceSync.saveChatMessage(chartId, role, text, tool || null);
    },

    remove(chartId) {
        if (!chartId) return;
        localStorage.removeItem(this._key(chartId));
    },

    restore(chartId) {
        this._restoring = true;
        var msgs = this.load(chartId);
        var container = document.getElementById('chat-messages');
        if (msgs.length === 0) {
            var mz = MingzhuManager.getAll().find(function(x) { return x.chart_id === chartId; });
            container.innerHTML = '<div class="chat-welcome"><p>已切换到 <b>' + _escHtml(mz ? mz.name : '命主') + '</b></p></div>';
        } else {
            container.innerHTML = '';
            msgs.forEach(function(m) { addChatMsg(m.role, m.text, m.tool); });
        }
        this._restoring = false;
    }
};

// ── CorrectionManager ──
export const CorrectionManager = {
    count: 0,

    reset() {
        this.count = 0;
        document.getElementById('correct-count').classList.add('hidden');
    },

    increment() {
        this.count++;
        const el = document.getElementById('correct-count');
        el.textContent = '✅ 已纠正 ' + this.count + ' 处';
        el.classList.remove('hidden');
    },

    startCorrection() {
        const inp = document.getElementById('chat-input');
        inp.placeholder = '请描述哪里分析不对…';
        inp.focus();
        document.getElementById('correct-btn').style.display = 'none';
        document.getElementById('chat-send-btn').textContent = '指正';
        document.getElementById('chat-send-btn').style.background = 'var(--gold)';
        document.getElementById('chat-send-btn').style.color = 'var(--ink)';
        this._correcting = true;
    },

    endCorrection() {
        const inp = document.getElementById('chat-input');
        inp.placeholder = '输入出生信息或问题…';
        document.getElementById('chat-send-btn').textContent = '发送';
        document.getElementById('chat-send-btn').style.background = 'var(--cinnabar)';
        document.getElementById('chat-send-btn').style.color = '#fff';
        this._correcting = false;
    },

    isCorrecting() {
        return !!this._correcting;
    }
};

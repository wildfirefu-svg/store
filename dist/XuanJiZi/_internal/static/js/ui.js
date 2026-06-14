// ================================================================
// 玄机子 Frontend — UI 交互
// ReportTabs / addChatMsg / refreshPanel / switchMingzhu / deleteMingzhu / showModal
// ================================================================

import { MingzhuManager, PersistenceSync, ChatHistory } from './state.js';
import { API } from './api.js';
import { renderMarkdown, _escHtml } from './markdown.js';
import { renderBaziTable } from './render-bazi.js';
import { renderZiweiTable, renderFullChart } from './render-ziwei.js';
export { _escHtml };

// ── ReportTabs ──
export const ReportTabs = {
    _cache: {},
    _active: 'overview',
    _currentChart: null,

    init(chartId) {
        this._currentChart = chartId || null;
        if (chartId && !this._cache[chartId]) {
            this._cache[chartId] = {};
        }
        this._active = 'overview';
        this._renderTabs();
        var store = this._getStore();
        var content = store['overview'] || '';
        var el = document.getElementById('report-content');
        var statusEl = document.getElementById('report-status');
        if (content) {
            if (el) el.innerHTML = renderMarkdown(content);
            if (statusEl) { statusEl.className = 'report-status done'; statusEl.textContent = '✓ 已加载'; }
        } else {
            if (el) el.innerHTML = '<p class="report-placeholder">输入出生信息后，报告将在此显示</p>';
            if (statusEl) { statusEl.className = 'report-status'; statusEl.textContent = ''; }
            document.getElementById('report-pdf-btn').classList.add('hidden');
        }
    },

    _getStore() {
        if (!this._currentChart) return {};
        if (!this._cache[this._currentChart]) this._cache[this._currentChart] = {};
        return this._cache[this._currentChart];
    },

    _renderTabs() {
        var container = document.getElementById('report-tabs');
        var correctEl = document.getElementById('correct-count');
        var store = this._getStore();
        container.innerHTML = '';
        var tabNames = {
            'overview': '总览',
            'deep_report': '深度报告',
            'sihechu': '四合出',
            'wealth': '财运',
            'marriage': '感情',
            'career': '事业',
            'hehun': '合婚',
            'name': '取名',
            'health': '健康',
            'zeri': '择日',
            'liunian': '流年',
        };
        function _tabLabel(tabId) {
            var numSuffix = '';
            var base = tabId;
            var m = tabId.match(/^(.+)_(\d+)$/);
            if (m) { base = m[1]; numSuffix = ' ' + _numCircle(parseInt(m[2])); }
            var label = tabNames[base] || base;
            return label + numSuffix;
        }
        function _numCircle(n) {
            var circles = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩','⑪','⑫','⑬','⑭','⑮'];
            return circles[n - 1] || '(' + n + ')';
        }
        ReportTabs._tabNames = tabNames;
        ReportTabs._tabLabel = _tabLabel;
        ReportTabs._numCircle = _numCircle;
        var displayTabs = {};
        if (store['overview'] !== undefined || true) displayTabs['overview'] = _tabLabel('overview');
        for (var tid in store) {
            if (tid === 'overview') continue;
            if (store[tid] !== undefined) displayTabs[tid] = _tabLabel(tid);
        }
        for (var tabId in displayTabs) {
            var span = document.createElement('span');
            span.className = 'report-tab' + (tabId === this._active ? ' active' : '');
            span.dataset.tab = tabId;
            span.setAttribute('role', 'tab');
            span.setAttribute('aria-selected', tabId === this._active ? 'true' : 'false');
            span.textContent = displayTabs[tabId];
            span.onclick = function(tid) { return function() { ReportTabs.switchTo(tid); }; }(tabId);
            container.appendChild(span);
        }
        if (correctEl) container.appendChild(correctEl);
    },

    set(tabId, content) {
        var store = this._getStore();
        store[tabId] = content;
        this._renderTabs();
    },

    switchTo(tabId) {
        this._active = tabId;
        this._renderTabs();
        var store = this._getStore();
        var content = store[tabId];
        if (content === undefined) {
            for (var tid in store) {
                if (store[tid] !== undefined) {
                    content = store[tid];
                    this._active = tid;
                    this._renderTabs();
                    break;
                }
            }
        }
        if (content !== undefined) {
            document.getElementById('report-content').innerHTML = renderMarkdown(content);
        }
    },

    getActive() {
        return this._active;
    }
};

// ── Chat & Panel UI ──
export function addChatMsg(role, text, tool) {
    const c = document.getElementById('chat-messages');
    const w = c.querySelector('.chat-welcome'); if (w) w.remove();
    const d = document.createElement('div');
    d.className = 'chat-msg ' + (role==='user'?'user':role==='system'?'system':'agent');
    const safeText = role === 'user' ? _escHtml(text) : text;
    d.innerHTML = '<div class="sender">' + (role==='user'?'您':role==='system'?'系统':'玄机子') + (tool?' <span class="tool-tag">🔧 '+tool+'</span>':'') + '</div><div class="bubble">' + safeText + '</div>';
    c.appendChild(d);
    const cur = MingzhuManager.getCurrent();
    if (cur && role !== 'system') { ChatHistory.append(cur.chart_id, role, text, tool); }
    if (c.scrollHeight - c.scrollTop - c.clientHeight < 50) c.scrollTop = c.scrollHeight;
    return d;
}

export function refreshPanel() {
    const list = MingzhuManager.getAll(), cur = MingzhuManager.getCurrent();
    document.getElementById('mingzhu-count').textContent = list.length + ' 个命盘';
    const container = document.getElementById('mingzhu-list');
    if (list.length === 0) { container.innerHTML = '<div class="mingzhu-empty">点击 ＋ 添加命主</div>'; return; }
    container.innerHTML = list.map(m =>
        '<div class="mingzhu-card' + (m.chart_id===cur?.chart_id?' active':'') + '" data-chart-id="' + _escHtml(m.chart_id) + '">' +
        '<span class="mingzhu-delete" data-delete-id="' + _escHtml(m.chart_id) + '" title="删除">×</span>' +
        '<div class="name">' + _escHtml(m.name) + '</div><div class="info">' + m.birth + '</div><div class="pattern">' + m.day_master + '</div></div>'
    ).join('') + '<div class="add-card" id="add-mingzhu-card-btn">＋</div>';
    // Bind event listeners (ES modules — no global onclick)
    container.querySelectorAll('.mingzhu-card').forEach(function(card) {
        card.addEventListener('click', function() { switchMingzhu(card.dataset.chartId); });
    });
    container.querySelectorAll('.mingzhu-delete').forEach(function(btn) {
        btn.addEventListener('click', function(e) { e.stopPropagation(); deleteMingzhu(btn.dataset.deleteId); });
    });
    var addBtn = document.getElementById('add-mingzhu-card-btn');
    if (addBtn) addBtn.addEventListener('click', showModal);
    document.getElementById('current-mingzhu-label').textContent = cur ? '当前：' + cur.name : '';
    ['hehun-p1','hehun-p2'].forEach(id => { const s=document.getElementById(id); if(s) s.innerHTML = list.map(m=>'<option value="'+_escHtml(m.chart_id)+'">'+_escHtml(m.name)+'</option>').join(''); });
}

export function switchMingzhu(chartId) {
    MingzhuManager.setCurrent(chartId); refreshPanel();
    var mz = MingzhuManager.getAll().find(function(x) { return x.chart_id === chartId; });
    var chatContainer = document.getElementById('chat-messages');
    chatContainer.innerHTML = '<div class="chat-welcome"><p>正在加载 <b>' + _escHtml(mz ? mz.name : '命主') + '</b> 的数据…</p></div>';
    ReportTabs.init(chartId);

    // Parallel fetch: chat history + reports
    if (mz && chartId) {
        Promise.allSettled([
            PersistenceSync.loadChatHistory(chartId).then(function(serverMsgs) {
                if (serverMsgs && serverMsgs.length > 0) {
                    localStorage.setItem('bazi_chat_' + chartId, JSON.stringify(serverMsgs));
                }
                ChatHistory.restore(chartId);
            }),
            PersistenceSync.loadReports(chartId).then(function(reports) {
                if (reports && Object.keys(reports).length > 0) {
                    ReportTabs._cache[chartId] = Object.assign(
                        ReportTabs._cache[chartId] || {}, reports
                    );
                    ReportTabs._renderTabs();
                }
                var store = ReportTabs._getStore();
                var firstTab = 'overview';
                for (var tid in store) {
                    if (tid !== 'overview' && store[tid] !== undefined) { firstTab = tid; break; }
                }
                ReportTabs.switchTo(firstTab);
            })
        ]).catch(function() {});
    } else {
        ChatHistory.restore(chartId);
        var store = ReportTabs._getStore();
        var firstTab = 'overview';
        for (var tid in store) {
            if (tid !== 'overview' && store[tid] !== undefined) { firstTab = tid; break; }
        }
        ReportTabs.switchTo(firstTab);
    }

    document.getElementById('bazi-table').innerHTML = '<p style="text-align:center;color:var(--text-tertiary);padding:20px">加载中…</p>';
    document.getElementById('ziwei-table').innerHTML = '';

    if (mz && mz._chart && mz._chart.four_pillars) {
        renderFullChart(mz._chart);
        return;
    }

    fetch(API + '/chart/' + chartId).then(r => r.json()).then(c => {
        if (c && c.four_pillars) {
            if (mz) { mz._chart = c; MingzhuManager.save(mz); }
            renderFullChart(c);
        } else {
            document.getElementById('bazi-table').innerHTML = '<p style="color:var(--coral);text-align:center;padding:8px">命盘缓存已过期，请重新添加命主</p>';
        }
    }).catch(function() {
        fetch(API + '/charts/' + chartId + '/data').then(function(r2) { return r2.json(); }).then(function(full) {
            if (full && full.chart_data && full.chart_data.four_pillars) {
                if (mz) { mz._chart = full.chart_data; MingzhuManager.save(mz); }
                renderFullChart(full.chart_data);
            } else {
                document.getElementById('bazi-table').innerHTML = '<p style="color:var(--coral);text-align:center;padding:8px">加载失败，请重新添加</p>';
            }
        }).catch(function() {
            document.getElementById('bazi-table').innerHTML = '<p style="color:var(--coral);text-align:center;padding:8px">加载失败，请重新添加</p>';
        });
    });
}

export function deleteMingzhu(chartId) {
    if (!confirm('确定删除？')) return;
    MingzhuManager.remove(chartId);
    ChatHistory.remove(chartId);
    PersistenceSync.deleteChartFromServer(chartId);
    const list = MingzhuManager.getAll();
    if (list.length > 0) { switchMingzhu(list[0].chart_id); } else {
        document.getElementById('chat-messages').innerHTML = '<div class="chat-welcome"><p>请添加命主</p></div>';
        document.getElementById('report-content').innerHTML = '<p class="report-placeholder">等待输入</p>';
        document.getElementById('bazi-table').innerHTML = '<p style="text-align:center;padding:20px">等待输入…</p>';
        document.getElementById('ziwei-table').innerHTML = '';
    }
    refreshPanel();
}

export function showModal() {
    document.getElementById('add-mingzhu-modal').classList.remove('hidden');
    document.getElementById('solar-time-check').checked = false;
    _solarOriginal = null;
}

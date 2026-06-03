// ================================================================
// 玄机子 Frontend v3 — rebuilt from working test page
// ================================================================
const API = '/api';

// ================================================================
// MingzhuManager
// ================================================================
const MingzhuManager = {
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

// ================================================================
// ChatHistory — per-mingzhu chat persistence (survives refresh)
// ================================================================
const ChatHistory = {
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
        catch { /* storage full — silently drop */ }
    },

    append(chartId, role, text, tool) {
        if (!chartId || this._restoring) return;
        var msgs = this.load(chartId);
        msgs.push({role: role, text: text, tool: tool || null});
        this.save(chartId, msgs);
        // Also persist to server
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

// ================================================================
// CorrectionManager — feedback loop for user corrections
// ================================================================
const CorrectionManager = {
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

// ================================================================
// PersistenceSync — API-backed data persistence
// ================================================================
const PersistenceSync = {
    // Fetch saved charts from server and merge into localStorage
    async loadFromServer() {
        try {
            var resp = await fetch(API + '/charts');
            if (!resp.ok) return;
            var charts = await resp.json();
            if (!charts || !charts.length) return;
            var local = MingzhuManager.getAll();
            for (var i = 0; i < charts.length; i++) {
                var c = charts[i];
                // Check if already in local list
                if (!local.find(function(m) { return m.chart_id === c.chart_id; })) {
                    // Fetch full chart data from server
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
            // Save merged list to localStorage
            localStorage.setItem('bazi_mingzhu_list', JSON.stringify(local));
        } catch(e) { /* server unavailable — use localStorage */ }
    },

    async saveChartToServer(chartId, name, birthInfo, chartData) {
        try {
            await fetch(API + '/charts/save', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({chart_id: chartId, name: name, birth_info: birthInfo, chart_data: chartData})
            });
        } catch(e) { /* silently fail */ }
    },

    async deleteChartFromServer(chartId) {
        try {
            await fetch(API + '/charts/' + chartId, {method: 'DELETE'});
        } catch(e) { /* silently fail */ }
    },

    async saveChatMessage(chartId, role, text, tool) {
        try {
            await fetch(API + '/charts/' + chartId + '/history', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({role: role, text: text, tool: tool || null})
            });
        } catch(e) { /* silently fail */ }
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
        } catch(e) { /* silently fail */ }
    },

    async loadReports(chartId) {
        try {
            var resp = await fetch(API + '/charts/' + chartId + '/reports');
            if (!resp.ok) return {};
            return await resp.json();
        } catch(e) { return {}; }
    }
};
// ================================================================
const ReportTabs = {
    _cache: {},       // chartId -> {tabId: content}
    _active: 'overview',
    _currentChart: null,

    init(chartId) {
        this._currentChart = chartId || null;
        if (chartId && !this._cache[chartId]) {
            this._cache[chartId] = {};
        }
        this._active = 'overview';
        this._renderTabs();
        // Immediately update report content for the new chart
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
        // Resolve tab label: "sihechu_2" → "四合出 ②"
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
        // Collect all tabs with content (including numbered variants)
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
        // If this tab has no content, fall back to first non-empty tab
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

// ================================================================
// PROVEN: chart rendering (from test_minimal)
// ================================================================
function renderBazi(chart) {
    if (!chart || !chart.four_pillars) { document.getElementById('bazi-table').innerHTML = '<p style="color:var(--coral);text-align:center;padding:8px">八字数据缺失</p>'; return; }
    const fp = chart.four_pillars, dm = chart.day_master, ds = chart.dayun_summary, ws = chart.wuxing_stats;
    const ss = chart.shensha || [];
    const dy = chart.da_yun || [];

    const wxCls = {'木':'wx-wood','火':'wx-fire','土':'wx-earth','金':'wx-metal','水':'wx-water'};
    function wxSpan(txt, wx) { return '<span class="'+(wxCls[wx]||'')+'">'+txt+'</span>'; }

    const cols = ['year','month','day','hour'];
    const colLabels = ['年柱','月柱','日柱','时柱'];
    const shenshaMap = {};
    const pmap = {year:'year_zhi',month:'month_zhi',day:'day_zhi',hour:'hour_zhi'};
    cols.forEach(k => { shenshaMap[k] = ss.filter(s => s.position === pmap[k]).map(s => s.name); });

    let h = '<div class="bazi-container">';
    // Four pillars
    h += '<div class="pillars-row">';
    for (let i = 0; i < cols.length; i++) {
        const k = cols[i], p = fp[k];
        const cg = p.cang_gan || [], css = p.cang_gan_shi_shen || [];
        const sha = shenshaMap[k] || [];
        const isDay = k === 'day';

        h += '<div class="pillar">';
        h += '<div class="pillar-label">' + colLabels[i] + '</div>';
        // 十神
        h += '<div class="pillar-shishen">' + (isDay ? '日主' : (p.shi_shen_gan || '—')) + '</div>';
        // 天干
        h += '<div class="pillar-gan">' + wxSpan(p.gan, p.gan_wuxing || '') + '</div>';
        // 地支
        h += '<div class="pillar-zhi">' + wxSpan(p.zhi, p.zhi_wuxing || '') + '</div>';
        // 藏干
        h += '<div class="pillar-canggan">';
        for (let j = 0; j < Math.max(cg.length, 1); j++) {
            const s = cg[j] || '—';
            const sss = css[j] || '';
            h += '<span class="cgl">' + s + (sss ? ' <span class="cgss">' + sss + '</span>' : '') + '</span>';
        }
        h += '</div>';
        // 纳音
        h += '<div class="pillar-nayin">' + (p.nayin || '—') + '</div>';
        // 神煞
        h += '<div class="pillar-shensha">';
        if (sha.length === 0) {
            h += '<span class="sht-empty">—</span>';
        } else {
            sha.forEach(sh => { h += '<span class="sht">' + sh + '</span>'; });
        }
        h += '</div>';

        h += '</div>';
    }
    h += '</div>';

    // 五行统计
    const wuMap = {'金':ws.jin||0,'木':ws.mu||0,'水':ws.shui||0,'火':ws.huo||0,'土':ws.tu||0};
    const wuDots = {'金':'wd-metal','木':'wd-wood','水':'wd-water','火':'wd-fire','土':'wd-earth'};
    h += '<div class="bazi-wuxing"><div class="wuxing-row">';
    ['金','木','水','火','土'].forEach(w => {
        h += '<div class="wuxing-item"><div class="wuxing-dot ' + wuDots[w] + '">' + w + '</div><div class="wuxing-count ' + wuDots[w] + '">' + wuMap[w] + '</div></div>';
    });
    h += '</div></div>';

    // 大运时间轴
    if (dy.length > 0) {
        h += '<div class="bazi-dayun"><div class="dayun-header">大运流年</div><div class="dayun-timeline">';
        var currentIdx = -1;
        dy.forEach(function(d, i) { if (d.is_current) currentIdx = i; });

        dy.forEach(function(d, i) {
            var cls = d.is_current ? ' current' : '';
            var pos = '';
            if (i === currentIdx - 1) pos = ' prev';
            if (i === currentIdx + 1) pos = ' next';
            if (i < currentIdx - 1) pos = ' far-past';
            if (i > currentIdx + 1) pos = ' far-future';

            h += '<div class="dayun-node' + cls + pos + '">';
            if (d.is_current) {
                h += '<div class="dayun-marker">▼ 当前</div>';
            }
            h += '<div class="dayun-ganzhi">' + wxSpan(d.gan, d.shi_shen_gan||'') + wxSpan(d.zhi, d.shi_shen_zhi||'') + '</div>';
            h += '<div class="dayun-ages">' + d.start_age + '–' + d.end_age + '岁</div>';
            h += '<div class="dayun-bar' + cls + '"></div>';
            h += '</div>';
        });
        h += '</div></div>';
    }

    h += '</div>'; // close bazi-container
    document.getElementById('bazi-table').innerHTML = h;
    document.getElementById('bazi-summary').innerHTML = '';
}

function renderZiwei(chart) {
    const el = document.getElementById('ziwei-table');
    if (!el) { console.error('ziwei-table element not found'); return; }
    const zw = chart.ziwei || {}, zi = zw.basic_info || {}, palaces = zw.twelve_palaces || [];
    if (palaces.length === 0) {
        el.innerHTML = '<p style="text-align:center;color:#ff6b6b;padding:10px">紫微数据缺失</p>';
        return;
    }
    const sihuaRaw = zw.si_hua || {};
    let sihua = [];
    if (Array.isArray(sihuaRaw)) { sihua = sihuaRaw; }
    else if (typeof sihuaRaw === 'object') { sihua = Object.entries(sihuaRaw).map(([type, info]) => ({...info, type})); }
    const bi = chart.birth_info || {}, fp = chart.four_pillars || {};

    // Star classification
    const MAIN_STARS = new Set(['紫微','天机','太阳','武曲','天同','廉贞','天府','太阴','贪狼','巨门','天相','天梁','七杀','破军']);
    const AUX_STARS = new Set(['文昌','文曲','天魁','天钺','左辅','右弼','禄存','天马']);
    const SHA_STARS = new Set(['擎羊','陀罗','火星','铃星','地空','地劫','天空']);
    const LOVE_STARS = new Set(['红鸾','天喜','天姚']);

    function classifyStar(s) {
        if (MAIN_STARS.has(s)) return 'star-main';
        if (AUX_STARS.has(s)) return 'star-aux';
        if (SHA_STARS.has(s)) return 'star-sha';
        if (LOVE_STARS.has(s)) return 'star-love';
        return 'star-small';
    }

    // Brightness CSS class and indicator
    function briClass(b) {
        return 'bri-' + ({'庙':'miao','旺':'wang','得':'de','平':'ping','陷':'xian'}[b] || 'none');
    }
    function briDot(b) {
        return '<span class="bri-dot ' + ({'庙':'miao','旺':'wang','得':'de','平':'ping','陷':'xian'}[b] || 'none') + '">●</span>';
    }

    // Build sihua map: starName → [type]
    const sihuaMap = {};
    sihua.forEach(sh => { if (!sh || !sh.star) return; if (!sihuaMap[sh.star]) sihuaMap[sh.star] = []; sihuaMap[sh.star].push(sh.type || ''); });

    // Fixed grid: earthly branch → {row, col}
    const ZHI_GRID = {
        '巳':{row:1,col:1}, '午':{row:1,col:2}, '未':{row:1,col:3}, '申':{row:1,col:4},
        '辰':{row:2,col:1}, '酉':{row:2,col:4},
        '卯':{row:3,col:1}, '戌':{row:3,col:4},
        '寅':{row:4,col:1}, '丑':{row:4,col:2}, '子':{row:4,col:3}, '亥':{row:4,col:4}
    };

    // 时辰 by hour pillar zhi
    const SHI_CHEN = {
        '子':'子时 (23:00–01:00)','丑':'丑时 (01:00–03:00)','寅':'寅时 (03:00–05:00)',
        '卯':'卯时 (05:00–07:00)','辰':'辰时 (07:00–09:00)','巳':'巳时 (09:00–11:00)',
        '午':'午时 (11:00–13:00)','未':'未时 (13:00–15:00)','申':'申时 (15:00–17:00)',
        '酉':'酉时 (17:00–19:00)','戌':'戌时 (19:00–21:00)','亥':'亥时 (21:00–23:00)'
    };

    // Build palace lookup by position
    const byZhi = {};
    palaces.forEach(p => { byZhi[p.position] = p; });

    function renderStar(sd) {
        // Handle both formats: string (legacy) or dict {name, brightness}
        const starName = typeof sd === 'string' ? sd : (sd.name || '');
        const brightness = typeof sd === 'string' ? '' : (sd.brightness || '');
        const cls = classifyStar(starName);
        const huaTypes = (sihuaMap[starName] || []).join('');
        const bDot = brightness ? briDot(brightness) : '';
        const bCls = brightness ? ' ' + briClass(brightness) : '';
        if (huaTypes) return '<span class="star star-hua' + bCls + '">' + starName + '(' + huaTypes + ')' + bDot + '</span>';
        return '<span class="star ' + cls + bCls + '">' + starName + bDot + '</span>';
    }

    let h = '<div class="ziwei-container"><div class="ziwei-grid">';

    // 12 palace cells
    for (const [zhi, pos] of Object.entries(ZHI_GRID)) {
        const p = byZhi[zhi] || {};
        const gz = (p.tian_gan || '') + zhi;
        const mainStars = p.main_stars || [], auxStars = p.auxiliary_stars || [];
        const isMing = p.name === '命宫', isShen = p.is_shengong;
        const name = (p.name || zhi).replace(/(.)/g, '$1 ').trim();

        h += '<div class="palace' + (isMing ? ' ming-palace' : '') + '" style="grid-row:' + pos.row + ';grid-column:' + pos.col + '">';
        h += '<div class="stars-area">';
        mainStars.forEach(s => { h += renderStar(s); });
        auxStars.forEach(s => { h += renderStar(s); });
        h += '</div>';
        h += '<div class="zhidi-area">' + gz + '</div>';
        h += '<div class="palace-name">' + name + (isShen ? ' (身)' : '') + '</div>';
        if (p.daxian) h += '<div class="liunian">' + p.daxian + '</div>';
        h += '</div>';
    }

    // Center info
    const genderLabel = (bi.gender || 'male') === 'male' ? '男' : '女';
    const bdate = (bi.year || '') + '-' + String(bi.month || '').padStart(2, '0') + '-' + String(bi.day || '').padStart(2, '0');
    const hourZhi = (fp.hour && fp.hour.zhi) ? fp.hour.zhi : '';
    const shichen = SHI_CHEN[hourZhi] || '';
    const sizhu = ['year', 'month', 'day', 'hour'].map(k => fp[k] ? fp[k].gan + fp[k].zhi : '??').join(' ');

    h += '<div class="center-info">';
    h += '<div class="center-row"><span class="label">性别</span> ' + genderLabel + '</div>';
    h += '<div class="center-row"><span class="label">五行局</span> ' + (zi.wu_xing_ju || '—') + '</div>';
    h += '<div class="center-row"><span class="label">阳历</span> ' + bdate + '</div>';
    if (shichen) h += '<div class="center-row"><span class="label">时辰</span> ' + shichen + '</div>';
    h += '<div class="center-row"><span class="label">命主</span> ' + (zi.ming_zhu || '—') + '  <span class="label">身主</span> ' + (zi.shen_zhu || '—') + '</div>';
    h += '<div class="center-sizhu">' + sizhu + '</div>';
    h += '</div>';

    h += '</div>'; // close ziwei-grid

    // Sihua bar
    if (sihua.length > 0) {
        h += '<div class="zw-sihua-bar">';
        sihua.forEach(sh => {
            const s = sh.type || '';
            h += '<span class="sihua-item"><span class="sihua-tag ' + (s === '化禄' ? 'lu' : s === '化权' ? 'quan' : s === '化科' ? 'ke' : 'ji') + '">' + s + '</span> → ' + (sh.star || '') + '</span>';
        });
        h += '</div>';
    }

    // Brightness legend
    h += '<div class="zw-legend">';
    h += '<span class="leg-item"><span class="bri-dot xian">●</span> 陷</span>';
    h += '<span class="leg-item"><span class="bri-dot ping">●</span> 平</span>';
    h += '<span class="leg-item"><span class="bri-dot de">●</span> 得</span>';
    h += '<span class="leg-item"><span class="bri-dot wang">●</span> 旺</span>';
    h += '<span class="leg-item"><span class="bri-dot miao">●</span> 庙</span>';
    h += '</div>';

    h += '</div>'; // close ziwei-container
    el.innerHTML = h;
}

function renderFullChart(chart) {
    try { renderBazi(chart); } catch(e) { console.error('renderBazi error:', e); document.getElementById('bazi-table').innerHTML = '<p style="color:red">八字渲染错误: ' + e.message + '</p>'; }
    try { renderZiwei(chart); } catch(e) { console.error('renderZiwei error:', e); document.getElementById('ziwei-table').innerHTML = '<p style="color:red">紫微渲染错误: ' + e.message + '</p>'; }
}

// ================================================================
// API helpers
// ================================================================
async function apiCreateChart(birth) {
    const r = await fetch(API + '/chart', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(birth) });
    return r.ok ? r.json() : null;
}
async function apiGenerateReport(chartId, mode) {
    const r = await fetch(API + '/analyze', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({chart_id:chartId, mode:mode}) });
    return r.ok ? (await r.json()).report : null;
}
function apiChatStream(chartId, message, onReplyDelta, onReportDelta, onToolStart, onDone) {
    var params = new URLSearchParams({chart_id: chartId, message: message});
    var url = '/api/chat/stream?' + params;
    var gotContent = false;
    var aborted = false;
    var reader = null;

    // Allow caller to abort
    var ctrl = new AbortController();

    fetch(url, {signal: ctrl.signal}).then(function(response) {
        if (!response.ok) {
            throw new Error('HTTP ' + response.status);
        }
        reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';

        function pump() {
            if (aborted) return;
            return reader.read().then(function(result) {
                if (result.done) {
                    // Stream ended naturally
                    if (!gotContent) {
                        onReplyDelta('\n\n⚠️ AI 服务连接失败。请确认：\n1. 已设置 DEEPSEEK_API_KEY，或在项目目录创建 .deepseek_key / .anthropic_key 文件\n2. API Key 有效且账户余额/额度可用\n3. 当前启动后端的终端可以访问 DeepSeek/Anthropic API', null);
                    }
                    onDone(0);
                    return;
                }
                buffer += decoder.decode(result.value, {stream: true});
                // Parse SSE events from buffer
                var lines = buffer.split('\n');
                // Keep last incomplete line in buffer
                buffer = lines.pop();
                var eventType = '';
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];
                    if (line.indexOf('event: ') === 0) {
                        eventType = line.slice(7).trim();
                    } else if (line.indexOf('data: ') === 0) {
                        var dataStr = line.slice(6);
                        try {
                            var data = JSON.parse(dataStr);
                            if (eventType === 'tool') {
                                gotContent = true;
                                onToolStart(data.name);
                            } else if (eventType === 'reply') {
                                gotContent = true;
                                onReplyDelta(data.text, data.tool || null);
                            } else if (eventType === 'report') {
                                gotContent = true;
                                onReportDelta(data.text, data.tab || 'overview');
                            } else if (eventType === 'done') {
                                onDone(data.corrections || 0);
                                aborted = true;
                                if (reader) { try { reader.cancel(); } catch(e) {} }
                                return;
                            }
                        } catch(e) { /* skip malformed JSON */ }
                    }
                }
                return pump();
            }).catch(function(e) {
                if (!gotContent) {
                    var detail = (e && e.message) ? e.message : String(e || '');
                    onReplyDelta('\n\n⚠️ AI 服务连接失败（' + detail + '）。\n请确认：\n1. 已设置 DEEPSEEK_API_KEY，或在项目目录创建 .deepseek_key / .anthropic_key 文件\n2. API Key 有效且账户余额/额度可用\n3. 当前启动后端的终端可以访问 DeepSeek/Anthropic API', null);
                }
                onDone(0);
            });
        }
        return pump();
    }).catch(function(e) {
        if (!gotContent) {
            var detail = (e && e.message) ? e.message : String(e || '');
            onReplyDelta('\n\n⚠️ AI 服务连接失败（' + detail + '）。\n请确认：\n1. 已设置 DEEPSEEK_API_KEY，或在项目目录创建 .deepseek_key / .anthropic_key 文件\n2. API Key 有效且账户余额/额度可用\n3. 当前启动后端的终端可以访问 DeepSeek/Anthropic API', null);
        }
        onDone(0);
    });
}

// ================================================================
// UI helpers
// ================================================================
function addChatMsg(role, text, tool) {
    const c = document.getElementById('chat-messages');
    const w = c.querySelector('.chat-welcome'); if (w) w.remove();
    const d = document.createElement('div');
    d.className = 'chat-msg ' + (role==='user'?'user':role==='system'?'system':'agent');
    const safeText = role === 'user' ? _escHtml(text) : text;
    d.innerHTML = '<div class="sender">' + (role==='user'?'您':role==='system'?'系统':'玄机子') + (tool?' <span class="tool-tag">🔧 '+tool+'</span>':'') + '</div><div class="bubble">' + safeText + '</div>';
    c.appendChild(d);
    // Persist to localStorage (per current mingzhu)
    const cur = MingzhuManager.getCurrent();
    if (cur && role !== 'system') { ChatHistory.append(cur.chart_id, role, text, tool); }
    // Only scroll if user is already at bottom (within 50px)
    if (c.scrollHeight - c.scrollTop - c.clientHeight < 50) c.scrollTop = c.scrollHeight;
    return d;
}
function refreshPanel() {
    const list = MingzhuManager.getAll(), cur = MingzhuManager.getCurrent();
    document.getElementById('mingzhu-count').textContent = list.length + ' 个命盘';
    const container = document.getElementById('mingzhu-list');
    if (list.length === 0) { container.innerHTML = '<div class="mingzhu-empty">点击 ＋ 添加命主</div>'; return; }
    container.innerHTML = list.map(m =>
        '<div class="mingzhu-card' + (m.chart_id===cur?.chart_id?' active':'') + '" onclick="switchMingzhu(\'' + m.chart_id + '\')">' +
        '<span class="mingzhu-delete" onclick="event.stopPropagation();deleteMingzhu(\'' + m.chart_id + '\')" title="删除">×</span>' +
        '<div class="name">' + _escHtml(m.name) + '</div><div class="info">' + m.birth + '</div><div class="pattern">' + m.day_master + '</div></div>'
    ).join('') + '<div class="add-card" onclick="showModal()">＋</div>';
    document.getElementById('current-mingzhu-label').textContent = cur ? '当前：' + cur.name : '';
    ['hehun-p1','hehun-p2'].forEach(id => { const s=document.getElementById(id); if(s) s.innerHTML = list.map(m=>'<option value="'+_escHtml(m.chart_id)+'">'+_escHtml(m.name)+'</option>').join(''); });
}
function switchMingzhu(chartId) {
    // Save current chat before switching away
    var prev = MingzhuManager.getCurrent();
    if (prev && prev.chart_id !== chartId) {
        // Current DOM messages are already persisted via addChatMsg,
        // so no extra save needed — just restore the target mingzhu.
    }
    MingzhuManager.setCurrent(chartId); refreshPanel();
    var mz = MingzhuManager.getAll().find(function(x) { return x.chart_id === chartId; });

    // Clear chat area immediately and show loading state
    var chatContainer = document.getElementById('chat-messages');
    chatContainer.innerHTML = '<div class="chat-welcome"><p>正在加载 <b>' + _escHtml(mz ? mz.name : '命主') + '</b> 的数据…</p></div>';

    ReportTabs.init(chartId);

    // Load chat history + reports from server if we have a chart
    if (mz && chartId) {
        PersistenceSync.loadChatHistory(chartId).then(function(serverMsgs) {
            if (serverMsgs && serverMsgs.length > 0) {
                localStorage.setItem('bazi_chat_' + chartId, JSON.stringify(serverMsgs));
            }
            // Always restore from best available source (server → localStorage)
            ChatHistory.restore(chartId);
        }).catch(function() {
            ChatHistory.restore(chartId);
        });
        PersistenceSync.loadReports(chartId).then(function(reports) {
            if (reports && Object.keys(reports).length > 0) {
                ReportTabs._cache[chartId] = Object.assign(
                    ReportTabs._cache[chartId] || {}, reports
                );
                ReportTabs._renderTabs();
            }
            // Show first available tab
            var store = ReportTabs._getStore();
            var firstTab = 'overview';
            for (var tid in store) {
                if (tid !== 'overview' && store[tid] !== undefined) { firstTab = tid; break; }
            }
            ReportTabs.switchTo(firstTab);
        }).catch(function() {});
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

    // 优先从 localStorage 恢复
    if (mz && mz._chart && mz._chart.four_pillars) {
        renderFullChart(mz._chart);
        return;
    }

    // Fallback: 从 API 缓存加载
    fetch(API + '/chart/' + chartId).then(r => r.json()).then(c => {
        if (c && c.four_pillars) {
            // 回存到 localStorage
            if (mz) { mz._chart = c; MingzhuManager.save(mz); }
            renderFullChart(c);
        } else {
            document.getElementById('bazi-table').innerHTML = '<p style="color:var(--coral);text-align:center;padding:8px">命盘缓存已过期，请重新添加命主</p>';
        }
    }).catch(function() {
        // Also try server DB if API cache fails
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
function deleteMingzhu(chartId) {
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
function showModal() {
    document.getElementById('add-mingzhu-modal').classList.remove('hidden');
    document.getElementById('solar-time-check').checked = false;
    _solarOriginal = null;
}
function _escHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function _renderMdTable(lines) {
    const parseRow = function(line) {
        return line.replace(/^\||\|$/g, '').split('|').map(function(c) { return _escHtml(c.trim()); });
    };
    const header = parseRow(lines[0]);
    let h = '<table><thead><tr>';
    header.forEach(function(c) { h += '<th>' + c + '</th>'; });
    h += '</tr></thead><tbody>';
    for (let i = 2; i < lines.length; i++) {
        const cells = parseRow(lines[i]);
        h += '<tr>';
        cells.forEach(function(c) { h += '<td>' + c + '</td>'; });
        h += '</tr>';
    }
    h += '</tbody></table>';
    return h;
}

function _renderMdBlock(block) {
    return block
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/\n/g, '<br>');
}

function renderMarkdown(md) {
    if (!md) return '';
    const blocks = md.split(/\n\n/);
    return blocks.map(function(block) {
        const lines = block.split('\n');
        if (lines.length >= 2 && lines[0].startsWith('|') && /^\|[\s\-:|]*\-+[\s\-:|]*\|$/.test(lines[1])) {
            return _renderMdTable(lines);
        }
        const nonEmpty = lines.filter(function(l) { return l.trim() !== ''; });
        if (nonEmpty.length > 0 && nonEmpty.every(function(l) { return /^- /.test(l); })) {
            return '<ul>' + nonEmpty.map(function(l) { return _renderMdBlock(l); }).join('') + '</ul>';
        }
        return _renderMdBlock(block);
    }).join('<br><br>');
}

function showReport(content) {
    document.getElementById('report-content').innerHTML = renderMarkdown(content);
}

function _sendWithStream(chartId, prompt, onSuccess, forceTab) {
    document.getElementById('report-status').classList.remove('done');
    document.getElementById('report-content').innerHTML =
        '<div class="report-loading"><div class="skeleton-line"></div><div class="skeleton-line w70"></div><div class="skeleton-line w50"></div></div>';

    const c = document.getElementById('chat-messages');
    const msgEl = document.createElement('div');
    msgEl.className = 'chat-msg agent';
    msgEl.innerHTML = '<div class="sender">玄机子</div><div class="bubble"><div class="ai-loading"><span></span><span></span><span></span></div></div>';
    c.appendChild(msgEl);
    const bubble = msgEl.querySelector('.bubble');

    let replyText = '';
    let currentTool = null;
    let reportBuf = '';
    let currentTab = forceTab || 'overview';
    const reportStatus = document.getElementById('report-status');

    apiChatStream(chartId, prompt,
        function(delta, tool) {
            if (tool) currentTool = tool;
            replyText += delta;
            bubble.innerHTML = replyText.replace(/\n/g, '<br>') + '<span class="streaming-cursor">▌</span>';
            if (c.scrollHeight - c.scrollTop - c.clientHeight < 50) {
                c.scrollTop = c.scrollHeight;
            }
        },
        function(text, tab) {
            // On first delta: create unique tab if base name already taken
            if (currentTab === 'overview' && tab !== 'overview') {
                var store = ReportTabs._getStore();
                var baseTab = tab;
                var counter = 1;
                while (store[tab] !== undefined) {
                    counter++;
                    tab = baseTab + '_' + counter;
                }
                currentTab = tab;
            }
            reportBuf = text;
            showReportStreaming(tab, reportBuf);
        },
        function(toolName) {
            currentTool = toolName;
            const sender = msgEl.querySelector('.sender');
            sender.innerHTML = '玄机子 <span class="tool-tag">🔧 ' + toolName + '</span>';
            reportStatus.innerHTML = '⏳ 玄机子正在' + toolName + '…';
        },
        function(corrections) {
            bubble.innerHTML = replyText.replace(/\n/g, '<br>') || '分析完成，请查看右侧报告。';
            reportStatus.innerHTML = '✅ 分析完成';
            if (reportBuf) showReportFinal(currentTab, reportBuf);
            if (currentTool) {
                const sender = msgEl.querySelector('.sender');
                sender.innerHTML = '玄机子 <span class="tool-tag">🔧 ' + currentTool + '</span>';
            }
            var correctBtn = document.getElementById('correct-btn');
            if (correctBtn) correctBtn.style.display = 'inline-block';
            if (onSuccess) onSuccess();
        }
    );
}

function ensureReportTab(tabId) {
    ReportTabs.set(tabId, '');
}

function activateReportTab(tabId) {
    ReportTabs.switchTo(tabId);
}

function showReportStreaming(tab, content) {
    var store = ReportTabs._getStore();
    store[tab] = content;
    ReportTabs._active = tab;
    ReportTabs._renderTabs();
    document.getElementById('report-content').innerHTML =
        renderMarkdown(content) + '<span class="streaming-cursor">▌</span>';
    document.getElementById('report-status').classList.remove('done');
}

function _buildOverview() {
    var store = ReportTabs._getStore();
    var baseNames = {sihechu:'四合出', wealth:'财运', marriage:'感情', career:'事业', hehun:'合婚', name:'取名', health:'健康', zeri:'择日', liunian:'流年'};
    var getLabel = ReportTabs._tabLabel || function(t) { return t; };
    var parts = [];
    for (var tid in store) {
        if (tid === 'overview') continue;
        if (store[tid]) {
            var h2s = store[tid].match(/^## (.+)$/gm);
            if (h2s && h2s.length > 0) {
                parts.push('#### ' + getLabel(tid));
                for (var i = 0; i < Math.min(h2s.length, 5); i++) {
                    parts.push('- ' + h2s[i].replace(/^## /, ''));
                }
            } else {
                parts.push('- **' + getLabel(tid) + '**：已有分析结果');
            }
        }
    }
    if (parts.length === 0) return '输入出生信息后，报告将在此显示';
    return '# 分析总览\n\n' + parts.join('\n');
}

function showReportFinal(tab, content) {
    var store = ReportTabs._getStore();
    store[tab] = content;
    store['overview'] = _buildOverview();
    ReportTabs._active = tab;
    ReportTabs._renderTabs();
    document.getElementById('report-content').innerHTML = renderMarkdown(content);
    document.getElementById('report-status').classList.add('done');
    document.getElementById('report-pdf-btn').classList.remove('hidden');
    // Persist report to server
    var cur = MingzhuManager.getCurrent();
    if (cur) { PersistenceSync.saveReport(cur.chart_id, tab, content); }
}

// ── PDF download ──
document.getElementById('report-pdf-btn').addEventListener('click', async function() {
    var cur = MingzhuManager.getCurrent();
    if (!cur) { alert('请先添加命主'); return; }
    var modeMap = {sihechu: 5, wealth: 1, marriage: 1, career: 1, health: 1, name: 1, hehun: 6};
    var mode = modeMap[ReportTabs.getActive()] || 1;
    try {
        var r = await fetch(API + '/analyze/pdf', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({chart_id: cur.chart_id, mode: mode})
        });
        if (!r.ok) { alert('PDF生成失败'); return; }
        var blob = await r.blob();
        var url = window.URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url; a.download = 'report_' + cur.chart_id + '.pdf';
        a.click();
        window.URL.revokeObjectURL(url);
    } catch(e) { alert('下载失败: ' + e.message); }
});

// ================================================================
// Solar time checkbox
// ================================================================
let _solarOriginal = null;
document.getElementById('solar-time-check').addEventListener('change', async function() {
    const hEl = document.getElementById('pick-hour'), mEl = document.getElementById('pick-minute');
    if (this.checked) {
        const h = parseInt(hEl.value) || 0;
        const m = parseInt(mEl.value) || 0;
        _solarOriginal = { hour: h, minute: m };

        const y = parseInt(document.getElementById('pick-year').value) || 2000;
        const mo = parseInt(document.getElementById('pick-month').value) || 1;
        const loc = document.getElementById('mingzhu-location').value || '北京';

        try {
            const r = await fetch('/api/solar-time', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({year: y, month: mo, day: 1, hour: h, minute: m, location: loc})
            });
            if (r.ok) {
                const d = await r.json();
                hEl.value = d.adjusted_hour; mEl.value = d.adjusted_minute;
            }
        } catch(e) { console.error('solar-time fetch error:', e); }
    } else {
        if (_solarOriginal) {
            hEl.value = _solarOriginal.hour; mEl.value = _solarOriginal.minute;
            _solarOriginal = null;
        }
    }
});

// ================================================================
// ── Chart tab switching ────────────────────────────────────────
document.querySelectorAll('.chart-tab').forEach(tab => {
    tab.addEventListener('click', function() {
        document.querySelectorAll('.chart-tab').forEach(t => t.classList.remove('active'));
        this.classList.add('active');
        const target = this.dataset.chart;
        document.getElementById('bazi-section').classList.toggle('hidden', target !== 'bazi');
        document.getElementById('ziwei-section').classList.toggle('hidden', target !== 'ziwei');
    });
});

// EVENT WIRING
// ================================================================

// Form submit
document.getElementById('mingzhu-submit-btn').addEventListener('click', async () => {
    const getV = id => { const el = document.getElementById(id); return parseInt(el.value) || 0; };
    const calType = document.querySelector('.toggle-btn.active')?.dataset?.cal || 'solar';
    let b = {
        year: getV('pick-year'), month: getV('pick-month'), day: getV('pick-day'),
        hour: getV('pick-hour'), minute: getV('pick-minute'),
        gender: document.getElementById('mingzhu-gender').value,
        location: document.getElementById('mingzhu-location').value || '北京',
        use_solar_time: document.getElementById('solar-time-check').checked
    };

    // Convert lunar to solar if needed
    if (calType === 'lunar') {
        try {
            const lr = await fetch('/api/lunar-to-solar', {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({year: b.year, month: b.month, day: b.day, is_leap: false})
            });
            if (lr.ok) {
                const ld = await lr.json();
                b.year = ld.solar_year; b.month = ld.solar_month; b.day = ld.solar_day;
            }
        } catch(e) { console.error('lunar convert error:', e); }
    }

    const name = document.getElementById('mingzhu-name').value || '命主';
    const btn = document.getElementById('mingzhu-submit-btn');
    btn.textContent = '排盘中…'; btn.disabled = true;

    const chart = await apiCreateChart(b);
    btn.textContent = '排盘'; btn.disabled = false;
    if (!chart) { alert('排盘失败'); return; }

    const mz = { chart_id: chart.chart_id, name: name,
        birth: b.year+'-'+String(b.month).padStart(2,'0')+'-'+String(b.day).padStart(2,'0')+' '+String(b.hour).padStart(2,'0')+':'+String(b.minute).padStart(2,'0'),
        gender: b.gender, day_master: chart.day_master.gan+chart.day_master.wuxing,
        _chart: chart };
    MingzhuManager.save(mz); MingzhuManager.setCurrent(chart.chart_id);
    // Persist to server
    PersistenceSync.saveChartToServer(chart.chart_id, name,
        {year: b.year, month: b.month, day: b.day, hour: b.hour, minute: b.minute, gender: b.gender, location: b.location},
        chart);
    ReportTabs.init(chart.chart_id);
    document.getElementById('add-mingzhu-modal').classList.add('hidden');
    refreshPanel();

    // Render chart
    renderFullChart(chart);

    // Chat greeting
    const g = b.gender==='male'?'男':'女';
    document.getElementById('chat-messages').innerHTML = '';
    addChatMsg('agent', '已为 <b>' + name + '</b> 排盘完毕。<br>出生：' + mz.birth + ' ' + g + ' ' + b.location + '<br>日主：<b>' + chart.day_master.gan + chart.day_master.wuxing + chart.day_master.yinyang + '</b><br><br>输入「<b>报告</b>」「<b>分析</b>」或具体问题开始解读。');

    // Auto-generate overview
    showReportFinal('overview', _buildAutoOverview(chart, mz));
    document.getElementById('chat-input').focus();
});

function _buildAutoOverview(chart, mz) {
    var dm = chart.day_master, fp = chart.four_pillars, ws = chart.wuxing_stats;
    var dy = chart.da_yun || [], ds = chart.dayun_summary || {};
    var cp = ds.current_pillar || (dy.length > 0 ? dy[3] : {});

    var md = '# 命盘总览\n\n';
    md += '## 日主\n';
    md += '**' + dm.gan + dm.wuxing + dm.yinyang + '**';
    if (dm.shier_changsheng) md += '　坐' + dm.shier_changsheng;
    md += '\n\n';

    md += '## 月令\n';
    var mp = fp.month;
    md += mp.gan + mp.zhi + '（' + mp.gan_wuxing + mp.zhi_wuxing + '）　十神：' + (mp.shi_shen_gan || '') + '\n\n';

    md += '## 五行偏枯\n';
    var wuOrder = ['金','木','水','火','土'];
    var wuPairs = wuOrder.map(function(w) { return [w, ws[w.toLowerCase().replace('火','huo').replace('水','shui').replace('木','mu').replace('金','jin').replace('土','tu')] || 0]; });
    wuPairs.sort(function(a,b) { return b[1] - a[1]; });
    var wuBars = wuPairs.map(function(p) { return p[0] + ' ' + '█'.repeat(Math.max(1, p[1])) + ' ' + p[1]; }).join('　');
    md += wuBars + '\n';
    if (ws.missing && ws.missing.length > 0) md += '\n⚠️ 缺：' + ws.missing.join('、') + '（参考紫微宫位补足）\n';
    md += '\n';

    md += '## 当前大运\n';
    if (cp.gan) {
        md += '**' + cp.gan + cp.zhi + '**　' + cp.start_age + '–' + cp.end_age + '岁（' + (cp.years || '') + '）\n';
        md += '\n起运：' + (ds.starting_age || '?') + '岁　方向：' + (ds.direction || '') + '\n';
    } else {
        md += '数据缺失\n';
    }
    md += '\n';

    md += '## 可问方向\n';
    md += '- 💰 财运　- 💕 感情　- 💼 事业\n';
    md += '- 🏥 健康　- 📖 学业　- 🔮 流年\n';
    md += '- 📅 择日　- 📆 流年运势　- ✏️ 取名\n';
    md += '\n';

    md += '## 可信度说明\n';
    md += '> 四柱排盘属于规则计算，确定性高。\n';
    md += '> 格局/用神/大运解读属于传统命理推断，依赖时辰准确性。\n';
    md += '> 健康/家庭/子女类判断对时辰高度敏感；时辰不准时仅作低置信参考。\n';
    md += '> 输入「报告」获取四合出（四派综合）深度分析。\n';

    return md;
}

function _expandPrompt(raw) {
    const kw = raw.replace(/\s/g, '');
    if (/^(报告|分析|帮我看看|看看|算|解读|详批|详测)$/.test(kw)) {
        return '请对此八字进行四合出（子平真诠+滴天髓+紫微斗数+盲派）综合分析，按以下12段结构输出完整报告：\n\n' +
            '## 一、八字排盘\n' +
            '## 二、共识结论（四派一致认定）\n' +
            '## 三、旺衰量化基准（得分表）\n' +
            '## 四、各派要点对比（表格）\n' +
            '## 五、各体系深度分析（子平/滴天髓/紫微/盲派各单独一节）\n' +
            '## 六、星平合参（八字←→紫微交叉验证）\n' +
            '## 七、分歧说明\n' +
            '## 八、应期共识（未来3年逐年预报）\n' +
            '## 九、纳音气质+五行补益\n' +
            '## 十、命理依据溯源\n' +
            '## 十一、命主画像（少年/青年/中年/晚年+当前大运+未来三年）\n' +
            '## 十二、免责声明\n\n' +
            '**输出要求**：\n' +
            '- 所有对比/统计类数据必须用 Markdown 表格\n' +
            '- 每张表格必须有表头行\n' +
            '- 评分用 ⭐ 视觉标记\n' +
            '- 每个判断给出理法依据和象法翻译\n' +
            '- 引用经典原文标注出处';
    }
    const tableRule = '\n\n**输出格式要求**：所有统计数据、对比信息、评分、运势时间线必须使用 Markdown 表格呈现，禁止用纯文本罗列数据。\n表格示例：\n| 列1 | 列2 |\n|---|---|\n| 值1 | 值2 |';
    if (/^(财运|钱|发财|投资)/.test(kw)) {
        return '请对此八字的财运进行深度分析，包括：日主旺衰能否担财、财星是否得力、食伤能否生财、比劫是否夺财、大运流年财运走势、最佳求财方向和行业建议。' + tableRule;
    }
    if (/^(感情|婚姻|结婚|恋爱|桃花|夫妻)/.test(kw)) {
        return '请对此八字的婚姻感情进行深度分析，包括：配偶宫状态、财官星与日主关系、婚姻宫有无冲合刑害、紫微夫妻宫解读、大运流年感情走势、改善建议。' + tableRule;
    }
    if (/^(事业|工作|官运|升职|跳槽|创业)/.test(kw)) {
        return '请对此八字的事业官运进行深度分析，包括：官杀状态、印星配合、食伤制杀、格局层次、适合行业和岗位类型、大运流年事业走势。' + tableRule;
    }
    return raw;
}

document.getElementById('chat-send-btn').addEventListener('click', function() {
    const inp = document.getElementById('chat-input');
    const text = inp.value.trim();
    if (!text) return;
    const cur = MingzhuManager.getCurrent();
    if (!cur) { showModal(); addChatMsg('agent', '请先添加命主并完成排盘，然后再开始分析。'); return; }

    // 指正模式
    if (CorrectionManager.isCorrecting()) {
        CorrectionManager.endCorrection();
        addChatMsg('user', '🔧 指正：' + text);
        inp.value = ''; inp.style.height = 'auto';
        const activeTab = ReportTabs.getActive();
        const prompt = '用户指出以下分析有误，请重新审视并修正报告中对应的章节（仅修正有误部分，保留其余内容不变）：\n\n用户反馈：' + text + '\n\n当前报告标签：' + activeTab;
        _sendWithStream(cur.chart_id, prompt, function() {
            CorrectionManager.increment();
        });
        return;
    }

    // 正常模式
    const prompt = _expandPrompt(text);
    addChatMsg('user', text);
    inp.value = ''; inp.style.height = 'auto';
    _sendWithStream(cur.chart_id, prompt);
});

// 指正按钮
document.getElementById('correct-btn').addEventListener('click', function() {
    CorrectionManager.startCorrection();
});
// Textarea auto-resize + Enter/Shift+Enter handling
var chatInput = document.getElementById('chat-input');
chatInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});
chatInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        document.getElementById('chat-send-btn').click();
    }
});

// Panel
document.getElementById('panel-toggle').addEventListener('click', () => document.getElementById('app-container').classList.toggle('panel-collapsed'));
document.getElementById('panel-add-btn').addEventListener('click', showModal);
document.getElementById('add-mingzhu-btn').addEventListener('click', showModal);
document.getElementById('add-mingzhu-modal').addEventListener('click', e => { if (e.target===e.currentTarget) e.currentTarget.classList.add('hidden'); });
document.getElementById('hehun-toggle-btn').addEventListener('click', () => document.getElementById('hehun-bar').classList.toggle('hidden'));
document.getElementById('hehun-close-btn').addEventListener('click', () => document.getElementById('hehun-bar').classList.add('hidden'));
document.getElementById('hehun-analyze-btn').addEventListener('click', async function() {
    const p1 = document.getElementById('hehun-p1').value;
    const p2 = document.getElementById('hehun-p2').value;
    if (p1 === p2) { alert('请选择两个不同的命主'); return; }
    document.getElementById('hehun-bar').classList.add('hidden');
    // Get raw data, then feed to AI for narrative report
    const r = await fetch(API + '/tools/hehun', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chart_id1: p1, chart_id2: p2 })
    });
    if (!r.ok) { alert('合婚计算失败'); return; }
    const d = await r.json();
    // Feed raw data to AI for detailed analysis
    var prompt = '请根据以下合婚原始数据，生成详细分析报告。要求：1. 总体评分和等级解读 2. 日主旺衰对比分析 3. 日支关系解读 4. 配偶星交互分析 5. 各维度得分详解 6. 综合建议。使用 Markdown 表格和 ⭐ 评分。\n\n合婚数据：\n' + JSON.stringify(d, null, 2);
    var cid = p1; // Use first person's chart for the stream
    _sendWithStream(cid, prompt, function() {
        ReportTabs.set('hehun', document.getElementById('report-content').innerHTML || '');
    }, 'hehun');
});

// ── Tool bars: zeri / liunian / name ──
function _hideToolBars() {
    ['zeri-bar','liunian-bar','name-bar','hehun-bar'].forEach(function(id) {
        document.getElementById(id).classList.add('hidden');
    });
}
function _showToolBar(barId) {
    _hideToolBars();
    document.getElementById(barId).classList.remove('hidden');
}

// Zeri (择日)
document.getElementById('zeri-toggle-btn').addEventListener('click', function() {
    var bar = document.getElementById('zeri-bar');
    if (bar.classList.contains('hidden')) {
        var now = new Date();
        document.getElementById('zeri-year').value = now.getFullYear();
        document.getElementById('zeri-month').value = now.getMonth() + 1;
        _showToolBar('zeri-bar');
    } else { bar.classList.add('hidden'); }
});
document.getElementById('zeri-close-btn').addEventListener('click', function() { document.getElementById('zeri-bar').classList.add('hidden'); });
document.getElementById('zeri-analyze-btn').addEventListener('click', async function() {
    var cur = MingzhuManager.getCurrent();
    if (!cur) { alert('请先添加命主'); return; }
    var y = parseInt(document.getElementById('zeri-year').value) || new Date().getFullYear();
    var m = parseInt(document.getElementById('zeri-month').value) || new Date().getMonth() + 1;
    var purpose = document.getElementById('zeri-purpose').value;
    var r = await fetch(API + '/tools/zeri', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({chart_id: cur.chart_id, year: y, month: m, purpose: purpose, top_n: 5})
    });
    if (!r.ok) { alert('查询失败'); return; }
    var d = await r.json();
    var md = '# 择日结果\n\n**' + d.purpose + '** ' + d.year + '年' + d.month + '月\n\n';
    (d.dates || []).forEach(function(dt, i) {
        md += '### ' + (i + 1) + '. ' + dt.date + '（' + dt.weekday + '）\n';
        md += '- 建除：' + (dt.ri_chen || '') + ' | 干支：' + (dt.ganzhi || '') + ' | 日干十神：' + (dt.shishen || '') + '\n';
        md += '- 评分：' + dt.score + '分 | ' + (dt.jianchu || '') + '\n';
        if (dt.detail) md += '- ' + dt.detail + '\n';
        md += '\n';
    });
    ReportTabs.set('zeri', md);
    ReportTabs.switchTo('zeri');
});

// Liunian (流年)
document.getElementById('liunian-toggle-btn').addEventListener('click', function() {
    var bar = document.getElementById('liunian-bar');
    if (bar.classList.contains('hidden')) {
        document.getElementById('liunian-year').value = new Date().getFullYear();
        _showToolBar('liunian-bar');
    } else { bar.classList.add('hidden'); }
});
document.getElementById('liunian-close-btn').addEventListener('click', function() { document.getElementById('liunian-bar').classList.add('hidden'); });
document.getElementById('liunian-analyze-btn').addEventListener('click', async function() {
    var cur = MingzhuManager.getCurrent();
    if (!cur) { alert('请先添加命主'); return; }
    var ty = parseInt(document.getElementById('liunian-year').value) || new Date().getFullYear();
    document.getElementById('liunian-bar').classList.add('hidden');
    var r = await fetch(API + '/tools/liunian', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({chart_id: cur.chart_id, target_year: ty})
    });
    if (!r.ok) { alert('查询失败'); return; }
    var d = await r.json();
    // Feed raw data to AI for detailed narrative
    var prompt = '请根据以下流年数据，生成 ' + ty + ' 年详细流年运势报告。要求：1. 年运总览 2. 每个月的详细分析（事业/财运/感情/健康四维度，用 ⭐ 评分）3. 最佳月份和最需注意的月份 4. 每月注意事项和建议。使用 Markdown 表格呈现每月运势。\n\n流年数据：\n' + JSON.stringify(d, null, 2);
    _sendWithStream(cur.chart_id, prompt, function() {
        ReportTabs.set('liunian', document.getElementById('report-content').innerHTML || '');
    }, 'liunian');
});

// Name (取名)
document.getElementById('name-toggle-btn').addEventListener('click', function() {
    var bar = document.getElementById('name-bar');
    if (bar.classList.contains('hidden')) { _showToolBar('name-bar'); }
    else { bar.classList.add('hidden'); }
});
document.getElementById('name-close-btn').addEventListener('click', function() { document.getElementById('name-bar').classList.add('hidden'); });
document.getElementById('name-tab-eval').addEventListener('click', function() {
    document.getElementById('name-tab-eval').classList.add('active');
    document.getElementById('name-tab-gen').classList.remove('active');
    document.getElementById('name-eval-fields').style.display = '';
    document.getElementById('name-gen-fields').style.display = 'none';
});
document.getElementById('name-tab-gen').addEventListener('click', function() {
    document.getElementById('name-tab-gen').classList.add('active');
    document.getElementById('name-tab-eval').classList.remove('active');
    document.getElementById('name-eval-fields').style.display = 'none';
    document.getElementById('name-gen-fields').style.display = '';
});
document.getElementById('name-analyze-btn').addEventListener('click', async function() {
    var cur = MingzhuManager.getCurrent();
    if (!cur) { alert('请先添加命主'); return; }
    var isEval = document.getElementById('name-tab-eval').classList.contains('active');
    if (isEval) {
        var name = document.getElementById('name-eval-name').value.trim();
        var gender = document.getElementById('name-eval-gender').value;
        if (!name) { alert('请输入姓名'); return; }
        var r = await fetch(API + '/tools/name/eval', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({chart_id: cur.chart_id, name: name, gender: gender})
        });
        if (!r.ok) { alert('查询失败'); return; }
        var d = await r.json();
        document.getElementById('name-bar').classList.add('hidden');
        // Feed raw data to AI for narrative report
        var prompt = '请根据以下名字评测原始数据，生成详细的名字分析报告。要求：1. 总分和等级解读 2. 五行匹配分析（名字五行 vs 八字喜用神）3. 五格数理详解 4. 三才配置解读 5. 音韵字义评价 6. 命名建议。使用 Markdown 表格呈现评分明细。\n\n姓名：' + name + '\n评测数据：\n' + JSON.stringify(d, null, 2);
        _sendWithStream(cur.chart_id, prompt, function() {
            ReportTabs.set('name', document.getElementById('report-content').innerHTML || '');
        }, 'name');
    } else {
        var surname = document.getElementById('name-gen-surname').value.trim();
        var gender = document.getElementById('name-gen-gender').value;
        if (!surname) { alert('请输入姓氏'); return; }
        var r = await fetch(API + '/tools/name/gen', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({chart_id: cur.chart_id, surname: surname, gender: gender, top_n: 5})
        });
        if (!r.ok) { alert('查询失败'); return; }
        var d = await r.json();
        document.getElementById('name-bar').classList.add('hidden');
        var candidates = Array.isArray(d) ? d : (d.names || d.candidates || []);
        var prompt = '请根据以下取名推荐数据，生成详细的名字推荐报告。要求：1. 推荐列表概览 2. 每个名字的五行匹配分析（对比八字喜用神）3. 每个名字的字义/音韵/寓意解读 4. 三才五格评价 5. 最终推荐排序和理由。使用 Markdown 表格对比评分。\n\n姓氏：' + surname + '　性别：' + gender + '\n推荐数据：\n' + JSON.stringify(candidates, null, 2);
        _sendWithStream(cur.chart_id, prompt, function() {
            ReportTabs.set('name', document.getElementById('report-content').innerHTML || '');
        }, 'name');
        });
        ReportTabs.set('name', md);
        ReportTabs.switchTo('name');
    }
});

// Calendar toggle buttons
document.querySelectorAll('.toggle-btn').forEach(b => b.addEventListener('click', () => { document.querySelectorAll('.toggle-btn').forEach(x=>x.classList.remove('active')); b.classList.add('active'); }));

// Mobile navigation
document.querySelectorAll('.mnav-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        const panel = this.dataset.panel;

        document.querySelectorAll('.mnav-btn').forEach(function(b) { b.classList.remove('active'); });
        this.classList.add('active');

        const chat = document.querySelector('.chat-column');
        const chart = document.querySelector('.chart-column');
        const report = document.querySelector('.report-column');
        const mingzhu = document.querySelector('.mingzhu-panel');

        [chat, chart, report, mingzhu].forEach(function(el) {
            el.classList.remove('mobile-visible', 'mobile-hidden');
        });

        if (panel === 'chat') {
            chat.classList.remove('mobile-hidden');
        } else if (panel === 'chart') {
            chat.classList.add('mobile-hidden');
            chart.classList.add('mobile-visible');
        } else if (panel === 'report') {
            chat.classList.add('mobile-hidden');
            report.classList.add('mobile-visible');
        } else if (panel === 'mingzhu') {
            chat.classList.add('mobile-hidden');
            mingzhu.classList.add('mobile-visible');
        }
    });
});

// Init — load from server, then restore panel + current mingzhu + chat history
(async function initApp() {
    // First, try to sync from server
    await PersistenceSync.loadFromServer();
    refreshPanel();

    var cur = MingzhuManager.getCurrent();
    if (!cur) {
        // No current mingzhu selected — try to pick first available
        var all = MingzhuManager.getAll();
        if (all.length > 0) {
            MingzhuManager.setCurrent(all[0].chart_id);
            cur = all[0];
            refreshPanel();
        }
    }

    ReportTabs.init(cur ? cur.chart_id : null);

    if (cur) {
        // Restore chart display
        if (cur._chart && cur._chart.four_pillars) {
            renderFullChart(cur._chart);
            document.getElementById('current-mingzhu-label').textContent = '当前：' + cur.name;
        } else {
            // Try to fetch from server
            try {
                var resp = await fetch(API + '/charts/' + cur.chart_id + '/data');
                if (resp.ok) {
                    var full = await resp.json();
                    if (full.chart_data && full.chart_data.four_pillars) {
                        cur._chart = full.chart_data;
                        MingzhuManager.save(cur);
                        renderFullChart(full.chart_data);
                        document.getElementById('current-mingzhu-label').textContent = '当前：' + cur.name;
                    }
                }
            } catch(e) { /* use whatever we have locally */ }
        }

        // Restore chat history — try server first, then localStorage
        var serverHistory = await PersistenceSync.loadChatHistory(cur.chart_id);
        if (serverHistory && serverHistory.length > 0) {
            localStorage.setItem('bazi_chat_' + cur.chart_id, JSON.stringify(serverHistory));
        }
        ChatHistory.restore(cur.chart_id);

        // Restore report tabs from server
        try {
            var serverReports = await PersistenceSync.loadReports(cur.chart_id);
            if (serverReports && Object.keys(serverReports).length > 0) {
                ReportTabs._cache[cur.chart_id] = serverReports;
                ReportTabs._renderTabs();
                // Show the overview or first tab
                var store = ReportTabs._getStore();
                var activeTab = ReportTabs._active || 'overview';
                var content = store[activeTab];
                if (content) {
                    var el = document.getElementById('report-content');
                    if (el) { el.innerHTML = renderMarkdown(content);
                        document.getElementById('report-status').className = 'report-status done';
                        document.getElementById('report-status').textContent = '✓ 已加载'; }
                }
            }
        } catch(e) { /* skip */ }
    }
})();

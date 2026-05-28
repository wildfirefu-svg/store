// ================================================================
// 玄机子 Frontend v3 — rebuilt from working test page
// ================================================================
const API = '/api';

// ================================================================
// MingzhuManager
// ================================================================
const MingzhuManager = {
    STORAGE_KEY: 'bazi_mingzhu_list',
    getAll() { try { return JSON.parse(sessionStorage.getItem(this.STORAGE_KEY)) || []; } catch { return []; } },
    save(mz) {
        const list = this.getAll(); const idx = list.findIndex(m => m.chart_id === mz.chart_id);
        if (idx >= 0) list[idx] = mz; else list.push(mz);
        sessionStorage.setItem(this.STORAGE_KEY, JSON.stringify(list)); return list;
    },
    remove(chartId) {
        const list = this.getAll().filter(m => m.chart_id !== chartId);
        sessionStorage.setItem(this.STORAGE_KEY, JSON.stringify(list));
        if (this.getCurrent()?.chart_id === chartId) sessionStorage.removeItem('bazi_current_mingzhu');
        return list;
    },
    getCurrent() { const id = sessionStorage.getItem('bazi_current_mingzhu'); return id ? this.getAll().find(m => m.chart_id === id) || null : null; },
    setCurrent(id) { sessionStorage.setItem('bazi_current_mingzhu', id); }
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
// ReportTabs — dynamic report tab management
// ================================================================
const ReportTabs = {
    _cache: {},
    _active: 'overview',

    init() {
        this._cache = {};
        this._active = 'overview';
        this._renderTabs();
    },

    _renderTabs() {
        const container = document.getElementById('report-tabs');
        const correctEl = document.getElementById('correct-count');
        container.innerHTML = '';
        const tabNames = {
            'overview': '总览',
            'sihechu': '四合出',
            'wealth': '财运专题',
            'marriage': '感情专题',
            'career': '事业专题',
            'hehun': '合婚',
            'name': '取名',
            'health': '健康',
        };
        for (const [tabId, label] of Object.entries(tabNames)) {
            if (this._cache[tabId] !== undefined || tabId === 'overview') {
                const span = document.createElement('span');
                span.className = 'report-tab' + (tabId === this._active ? ' active' : '');
                span.dataset.tab = tabId;
                span.textContent = label;
                span.onclick = function() { ReportTabs.switchTo(tabId); };
                container.appendChild(span);
            }
        }
        if (correctEl) container.appendChild(correctEl);
    },

    set(tabId, content) {
        this._cache[tabId] = content;
        this._renderTabs();
    },

    switchTo(tabId) {
        this._active = tabId;
        this._renderTabs();
        const content = this._cache[tabId] || '';
        document.getElementById('report-content').innerHTML = renderMarkdown(content);
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
        h += '<div class="wuxing-item"><div class="wuxing-dot ' + wuDots[w] + '">' + w + '</div><div class="wuxing-count">' + wuMap[w] + '</div></div>';
    });
    h += '</div></div>';

    // 大运
    if (dy.length > 0) {
        h += '<div class="bazi-dayun"><div class="dayun-row">';
        dy.forEach(d => {
            const cur = d.is_current ? ' current' : '';
            h += '<div class="dayun-item' + cur + '">';
            h += '<div class="dayun-age">' + d.start_age + '–' + d.end_age + '</div>';
            h += '<div class="dayun-gz">' + wxSpan(d.gan, (dm.gan_wuxing||'')) + wxSpan(d.zhi, (dm.zhi_wuxing||'')) + '</div>';
            h += '<div class="dayun-ss">' + (d.shi_shen_gan || '') + '</div>';
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
    const params = new URLSearchParams({chart_id: chartId, message: message});
    const es = new EventSource('/api/chat/stream?' + params);

    es.addEventListener('tool', function(e) {
        const data = JSON.parse(e.data);
        onToolStart(data.name);
    });

    es.addEventListener('reply', function(e) {
        const data = JSON.parse(e.data);
        onReplyDelta(data.text, data.tool || null);
    });

    es.addEventListener('report', function(e) {
        const data = JSON.parse(e.data);
        onReportDelta(data.text, data.tab || 'overview');
    });

    es.addEventListener('done', function(e) {
        const data = JSON.parse(e.data);
        onDone(data.corrections || 0);
        es.close();
    });

    es.addEventListener('error', function() {
        es.close();
        onReplyDelta('\n\n⚠️ AI 服务连接失败。请确认：\n1. 已在项目目录创建 .anthropic_key 文件\n2. API Key 有效且未过期\n3. 网络可访问 api.anthropic.com', null);
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
    MingzhuManager.setCurrent(chartId); refreshPanel();
    const mz = MingzhuManager.getAll().find(m => m.chart_id === chartId);
    document.getElementById('chat-messages').innerHTML = '<div class="chat-welcome"><p>已切换到 <b>' + _escHtml(mz?mz.name:'命主') + '</b></p></div>';
    document.getElementById('report-content').innerHTML = '';
    document.getElementById('bazi-table').innerHTML = '<p style="text-align:center;color:var(--text-tertiary);padding:20px">加载中…</p>';
    document.getElementById('ziwei-table').innerHTML = '';

    // 优先从 sessionStorage 恢复
    if (mz && mz._chart && mz._chart.four_pillars) {
        renderFullChart(mz._chart);
        return;
    }

    // Fallback: 从 API 缓存加载
    fetch(API + '/chart/' + chartId).then(r => r.json()).then(c => {
        if (c && c.four_pillars) {
            // 回存到 sessionStorage
            if (mz) { mz._chart = c; MingzhuManager.save(mz); }
            renderFullChart(c);
        } else {
            document.getElementById('bazi-table').innerHTML = '<p style="color:var(--coral);text-align:center;padding:8px">命盘缓存已过期，请重新添加命主</p>';
        }
    }).catch(() => {
        document.getElementById('bazi-table').innerHTML = '<p style="color:var(--coral);text-align:center;padding:8px">加载失败，请重新添加</p>';
    });
}
function deleteMingzhu(chartId) {
    if (!confirm('确定删除？')) return;
    MingzhuManager.remove(chartId);
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

function _sendWithStream(chartId, prompt, onSuccess) {
    document.getElementById('report-status').classList.remove('done');
    document.getElementById('report-content').innerHTML =
        '<div class="report-loading"><div class="skeleton-line"></div><div class="skeleton-line w70"></div><div class="skeleton-line w50"></div></div>';

    const c = document.getElementById('chat-messages');
    const msgEl = document.createElement('div');
    msgEl.className = 'chat-msg agent';
    msgEl.innerHTML = '<div class="sender">玄机子</div><div class="bubble"><span class="loading-spin">⏳</span> 思考中…</div>';
    c.appendChild(msgEl);
    const bubble = msgEl.querySelector('.bubble');

    let replyText = '';
    let currentTool = null;
    let reportBuf = '';
    let currentTab = 'overview';
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
            currentTab = tab;
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
    if (ReportTabs._cache[tabId] === undefined) {
        ReportTabs.set(tabId, '');
    }
}

function activateReportTab(tabId) {
    ReportTabs.switchTo(tabId);
}

function showReportStreaming(tab, content) {
    ReportTabs._cache[tab] = content;
    ReportTabs._active = tab;
    ReportTabs._renderTabs();
    document.getElementById('report-content').innerHTML =
        renderMarkdown(content) + '<span class="streaming-cursor">▌</span>';
    document.getElementById('report-status').classList.remove('done');
}

function showReportFinal(tab, content) {
    ReportTabs._cache[tab] = content;
    ReportTabs._active = tab;
    ReportTabs._renderTabs();
    document.getElementById('report-content').innerHTML = renderMarkdown(content);
    document.getElementById('report-status').classList.add('done');
}

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
    document.getElementById('add-mingzhu-modal').classList.add('hidden');
    refreshPanel();

    // Render chart
    renderFullChart(chart);

    // Chat greeting
    const g = b.gender==='male'?'男':'女';
    document.getElementById('chat-messages').innerHTML = '';
    addChatMsg('agent', '已为 <b>' + name + '</b> 排盘完毕。<br>出生：' + mz.birth + ' ' + g + ' ' + b.location + '<br>日主：<b>' + chart.day_master.gan + chart.day_master.wuxing + chart.day_master.yinyang + '</b><br><br>输入「<b>报告</b>」「<b>分析</b>」或具体问题开始解读。');

    document.getElementById('report-content').innerHTML = '';
    document.getElementById('chat-input').focus();
});

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
    if (!cur) { addChatMsg('agent', '请先添加命主。'); return; }

    // 指正模式
    if (CorrectionManager.isCorrecting()) {
        CorrectionManager.endCorrection();
        addChatMsg('user', '🔧 指正：' + text);
        inp.value = '';
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
    inp.value = '';
    _sendWithStream(cur.chart_id, prompt);
});

// 指正按钮
document.getElementById('correct-btn').addEventListener('click', function() {
    CorrectionManager.startCorrection();
});
document.getElementById('chat-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); document.getElementById('chat-send-btn').click(); }
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
    const r = await fetch(API + '/tools/hehun', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chart_id1: p1, chart_id2: p2 })
    });
    if (r.ok) {
        const d = await r.json();
        let m = '# 合婚分析\n\n<div class="score-card"><div class="big">' + d.total + '分</div><div class="grade">' + d.grade + '</div></div>\n';
        for (const [k, v] of Object.entries(d.scores || {})) {
            m += '## ' + k + '\n' + (v.detail || '') + '\n\n';
        }
        ReportTabs.set('hehun', m);
        ReportTabs.switchTo('hehun');
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

// Init — restore panel + current mingzhu on page refresh
refreshPanel();
ReportTabs.init();
(function restoreCurrent() {
    const cur = MingzhuManager.getCurrent();
    if (cur && cur._chart && cur._chart.four_pillars) {
        renderFullChart(cur._chart);
        document.getElementById('current-mingzhu-label').textContent = '当前：' + cur.name;
    }
})();

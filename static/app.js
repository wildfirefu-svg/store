// ================================================================
// 玄机子 Frontend v3 — 入口文件
// 模块化拆分：api.js / state.js / markdown.js / render-bazi.js /
//   render-ziwei.js / ui.js / stream.js 已独立加载
// ================================================================

import { API, apiCreateChart, apiChatStream } from './js/api.js';
import { MingzhuManager, PersistenceSync, ChatHistory, CorrectionManager } from './js/state.js';
import { renderMarkdown, _escHtml } from './js/markdown.js';
import { renderBaziTable } from './js/render-bazi.js';
import { renderZiweiTable, renderFullChart } from './js/render-ziwei.js';
import { ReportTabs, addChatMsg, refreshPanel, switchMingzhu, deleteMingzhu, showModal } from './js/ui.js';
import { _sendWithStream, showReportFinal } from './js/stream.js';
import { BaZiCharts } from './js/charts.js';

// ── 辅助函数 ──
function _hideToolBars() {
    ['hehun-bar','zeri-bar','liunian-bar','name-bar'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });
}
function _showToolBar(barId) {
    _hideToolBars();
    document.getElementById(barId).classList.remove('hidden');
}

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
    } else { md += '数据缺失\n'; }
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
    // 深度报告：15章完整模板
    if (/^(深度报告|深度分析|深度解读|深度详批|深度)$/.test(kw)) {
        window._forceDeepReport = true;
        return '请严格遵循系统提示词中的通用命盘分析模板（15章完整版），生成八字命盘深度分析报告。每章标题、每个表格列均不可跳过。\n\n必须包含全部15章：一、八字排盘 | 二、五行力量分析（量化表+流通路径+旺衰表）| 三、格局判定 | 四、用神体系（六位表）| 五、十神全局统计 | 六、刑冲合会深度解析（关系总表+重点解读）| 七、神煞系统（吉神/凶煞/特殊组合）| 八、大运分析（10步列表+当前大运详解+人生关键年份）| 九、七维人生解读（性格/事业/财运/感情/健康/学业/流年）| 十、胎元命宫身宫 | 十一、五行补益 | 十二、命理溯源 | 十三、行动纲领（P0/P1/P2+时间窗口）| 十四、综合总结精华（8条）| 十五、附录速查卡 | 免责声明\n\n输出要求：每章标题## N、章节名，所有数据用Markdown表格，star评分不全部同级，每个判断附依据。数据不足时写—，不删表格列。';
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

// ── 事件绑定 ──

// 发送按钮
document.getElementById('chat-send-btn').addEventListener('click', function() {
    const inp = document.getElementById('chat-input');
    const text = inp.value.trim();
    if (!text) return;
    const cur = MingzhuManager.getCurrent();
    if (!cur) { showModal(); addChatMsg('agent', '请先添加命主并完成排盘，然后再开始分析。'); return; }

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

    var isDeep = window._forceDeepReport || false;
    window._forceDeepReport = false;
    const prompt = _expandPrompt(text);
    addChatMsg('user', text);
    inp.value = ''; inp.style.height = 'auto';
    _sendWithStream(cur.chart_id, prompt, null, isDeep ? 'deep_report' : null);
});

// 指正按钮
document.getElementById('correct-btn').addEventListener('click', function() {
    CorrectionManager.startCorrection();
});

// Textarea auto-resize
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

// Panel toggle
document.getElementById('panel-toggle').addEventListener('click', function() {
    document.getElementById('app-container').classList.toggle('panel-collapsed');
});
document.getElementById('panel-add-btn').addEventListener('click', showModal);
document.getElementById('add-mingzhu-btn').addEventListener('click', showModal);
document.getElementById('add-mingzhu-modal').addEventListener('click', function(e) {
    if (e.target === e.currentTarget) e.currentTarget.classList.add('hidden');
});

// ── PDF 下载 ──
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

document.getElementById('visualization-btn').addEventListener('click', async function() {
    var cur = MingzhuManager.getCurrent();
    if (!cur) { alert('请先添加命主'); return; }
    var el = document.getElementById('report-content');
    el.innerHTML = '<div class="chart-grid"><div class="chart-card"><div id="viz-wuxing" class="chart-container"></div></div><div class="chart-card"><div id="viz-shishen" class="chart-container"></div></div><div class="chart-card"><div id="viz-dayun" class="chart-container"></div></div><div class="chart-card"><div id="viz-liunian" class="chart-container"></div></div></div>';
    try {
        var r = await fetch(API + '/charts/' + cur.chart_id + '/visualization');
        if (!r.ok) throw new Error('图表数据加载失败');
        var data = await r.json();
        BaZiCharts.renderWuxingRadar(document.getElementById('viz-wuxing'), data.wuxing || {});
        BaZiCharts.renderShishenPie(document.getElementById('viz-shishen'), data.shishen || {});
        BaZiCharts.renderDayunTrend(document.getElementById('viz-dayun'), data.dayun || []);
        BaZiCharts.renderLiunianBar(document.getElementById('viz-liunian'), data.liunian || []);
    } catch (e) {
        el.innerHTML = '<p class="report-placeholder">' + e.message + '</p>';
    }
});

// ── Solar time checkbox ──
window._solarOriginal = null;
document.getElementById('solar-time-check').addEventListener('change', async function() {
    const hEl = document.getElementById('pick-hour'), mEl = document.getElementById('pick-minute');
    if (this.checked) {
        const h = parseInt(hEl.value) || 0;
        const m = parseInt(mEl.value) || 0;
        window._solarOriginal = { hour: h, minute: m };
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
        if (window._solarOriginal) {
            hEl.value = window._solarOriginal.hour; mEl.value = window._solarOriginal.minute;
            window._solarOriginal = null;
        }
    }
});

// ── Chart tab switching ──
document.querySelectorAll('.chart-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
        document.querySelectorAll('.chart-tab').forEach(function(t) {
            t.classList.remove('active');
            t.setAttribute('aria-selected', 'false');
        });
        this.classList.add('active');
        this.setAttribute('aria-selected', 'true');
        const target = this.dataset.chart;
        document.getElementById('bazi-section').classList.toggle('hidden', target !== 'bazi');
        document.getElementById('ziwei-section').classList.toggle('hidden', target !== 'ziwei');
    });
});

// ── Calendar toggle ──
document.querySelectorAll('.toggle-btn').forEach(function(b) {
    b.addEventListener('click', function() {
        document.querySelectorAll('.toggle-btn').forEach(function(x) { x.classList.remove('active'); });
        b.classList.add('active');
    });
});

// ── 排盘提交 ──
document.getElementById('mingzhu-submit-btn').addEventListener('click', async function() {
    const getV = function(id) { const el = document.getElementById(id); return parseInt(el.value) || 0; };
    const calType = document.querySelector('.toggle-btn.active')?.dataset?.cal || 'solar';
    let b = {
        year: getV('pick-year'), month: getV('pick-month'), day: getV('pick-day'),
        hour: getV('pick-hour'), minute: getV('pick-minute'),
        gender: document.getElementById('mingzhu-gender').value,
        location: document.getElementById('mingzhu-location').value || '北京',
        use_solar_time: document.getElementById('solar-time-check').checked
    };

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
    PersistenceSync.saveChartToServer(chart.chart_id, name,
        {year: b.year, month: b.month, day: b.day, hour: b.hour, minute: b.minute, gender: b.gender, location: b.location},
        chart);
    ReportTabs.init(chart.chart_id);
    document.getElementById('add-mingzhu-modal').classList.add('hidden');
    refreshPanel();

    renderFullChart(chart);

    const g = b.gender==='male'?'男':'女';
    document.getElementById('chat-messages').innerHTML = '';
    addChatMsg('agent', '已为 <b>' + _escHtml(name) + '</b> 排盘完毕。<br>出生：' + mz.birth + ' ' + g + ' ' + _escHtml(b.location) + '<br>日主：<b>' + chart.day_master.gan + chart.day_master.wuxing + chart.day_master.yinyang + '</b><br><br>输入「<b>报告</b>」「<b>分析</b>」或具体问题开始解读。');

    showReportFinal('overview', _buildAutoOverview(chart, mz));
    document.getElementById('chat-input').focus();
});

// ── 合婚 ──
document.getElementById('hehun-toggle-btn').addEventListener('click', function() {
    document.getElementById('hehun-bar').classList.toggle('hidden');
});
document.getElementById('hehun-close-btn').addEventListener('click', function() {
    document.getElementById('hehun-bar').classList.add('hidden');
});
document.getElementById('hehun-analyze-btn').addEventListener('click', async function() {
    const p1 = document.getElementById('hehun-p1').value;
    const p2 = document.getElementById('hehun-p2').value;
    if (p1 === p2) { alert('请选择两个不同的命主'); return; }
    document.getElementById('hehun-bar').classList.add('hidden');
    const r = await fetch(API + '/tools/hehun', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chart_id1: p1, chart_id2: p2 })
    });
    if (!r.ok) { alert('合婚计算失败'); return; }
    const d = await r.json();
    var prompt = '请严格按照系统提示词中的"合婚分析模板"格式，根据以下数据生成合婚报告。必须包含：总体评分表、日主旺衰对比、日支关系、优势与风险、综合建议。\n\n合婚数据：\n' + JSON.stringify(d, null, 2);
    _sendWithStream(p1, prompt, function() {
        ReportTabs.set('hehun', document.getElementById('report-content').innerHTML || '');
    }, 'hehun');
});

// ── 择日 ──
document.getElementById('zeri-toggle-btn').addEventListener('click', function() {
    var bar = document.getElementById('zeri-bar');
    if (bar.classList.contains('hidden')) {
        var now = new Date();
        document.getElementById('zeri-year').value = now.getFullYear();
        document.getElementById('zeri-month').value = now.getMonth() + 1;
        _showToolBar('zeri-bar');
    } else { bar.classList.add('hidden'); }
});
document.getElementById('zeri-close-btn').addEventListener('click', function() {
    document.getElementById('zeri-bar').classList.add('hidden');
});
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

// ── 流年 ──
document.getElementById('liunian-toggle-btn').addEventListener('click', function() {
    var bar = document.getElementById('liunian-bar');
    if (bar.classList.contains('hidden')) {
        document.getElementById('liunian-year').value = new Date().getFullYear();
        _showToolBar('liunian-bar');
    } else { bar.classList.add('hidden'); }
});
document.getElementById('liunian-close-btn').addEventListener('click', function() {
    document.getElementById('liunian-bar').classList.add('hidden');
});
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
    var prompt = '请严格按照系统提示词中的"流年分析模板"格式，根据以下数据生成' + ty + '年流年运势报告。必须包含：年运总览+年度关键词、月度运势表（12个月×5列）、最佳月份、需注意的月份、年度建议。\n\n流年数据：\n' + JSON.stringify(d, null, 2);
    _sendWithStream(cur.chart_id, prompt, function() {
        ReportTabs.set('liunian', document.getElementById('report-content').innerHTML || '');
    }, 'liunian');
});

// ── 取名 ──
document.getElementById('name-toggle-btn').addEventListener('click', function() {
    var bar = document.getElementById('name-bar');
    if (bar.classList.contains('hidden')) { _showToolBar('name-bar'); }
    else { bar.classList.add('hidden'); }
});
document.getElementById('name-close-btn').addEventListener('click', function() {
    document.getElementById('name-bar').classList.add('hidden');
});
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
        var prompt = '请严格按照系统提示词中的"名字分析模板"格式，根据以下数据生成名字评测报告。必须包含：总分+等级、评分明细表（4维度）、五格数理表（5格）、五行匹配分析、建议。\n\n姓名：' + name + '\n评测数据：\n' + JSON.stringify(d, null, 2);
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
        var prompt = '请严格按照系统提示词中的"名字分析模板"格式，为以下候选名字逐一评测并排序。必须包含：总排名表、每个名字的评分明细表+五格数理表+五行匹配分析。\n\n姓氏：' + surname + '　性别：' + gender + '\n候选名字：\n' + JSON.stringify(candidates, null, 2);
        _sendWithStream(cur.chart_id, prompt, function() {
            ReportTabs.set('name', document.getElementById('report-content').innerHTML || '');
        }, 'name');
    }
});

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

// ── 初始化 ──
(async function initApp() {
    await PersistenceSync.loadFromServer();
    refreshPanel();

    var cur = MingzhuManager.getCurrent();
    if (!cur) {
        var all = MingzhuManager.getAll();
        if (all.length > 0) {
            MingzhuManager.setCurrent(all[0].chart_id);
            cur = all[0];
            refreshPanel();
        }
    }

    ReportTabs.init(cur ? cur.chart_id : null);

    if (cur) {
        if (cur._chart && cur._chart.four_pillars) {
            renderFullChart(cur._chart);
            document.getElementById('current-mingzhu-label').textContent = '当前：' + cur.name;
        } else {
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
            } catch(e) {}
        }

        var serverHistory = await PersistenceSync.loadChatHistory(cur.chart_id);
        if (serverHistory && serverHistory.length > 0) {
            localStorage.setItem('bazi_chat_' + cur.chart_id, JSON.stringify(serverHistory));
        }
        ChatHistory.restore(cur.chart_id);

        try {
            var serverReports = await PersistenceSync.loadReports(cur.chart_id);
            if (serverReports && Object.keys(serverReports).length > 0) {
                ReportTabs._cache[cur.chart_id] = serverReports;
                ReportTabs._renderTabs();
                var store = ReportTabs._getStore();
                var activeTab = ReportTabs._active || 'overview';
                var content = store[activeTab];
                if (content) {
                    var el = document.getElementById('report-content');
                    if (el) {
                        el.innerHTML = renderMarkdown(content);
                        document.getElementById('report-status').className = 'report-status done';
                        document.getElementById('report-status').textContent = '✓ 已加载';
                    }
                }
            }
        } catch(e) {}
    }
})();

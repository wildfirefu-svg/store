import { API } from './api.js';

export async function renderTimeline(container, chartId) {
    try {
        const [timelineResp, eventsResp] = await Promise.all([
            fetch(`${API}/charts/${chartId}/timeline`),
            fetch(`${API}/charts/${chartId}/life-events`),
        ]);

        if (!timelineResp.ok) throw new Error('Timeline data load failed');

        const timeline = await timelineResp.json();
        const userEvents = timelineResp.ok && timeline.user_events ? timeline.user_events : [];
        const eventMappings = timeline.event_mappings_by_year || {};
        const futureWarnings = timeline.future_warnings || [];
        const domains = timeline.domains || [];
        const birthYear = timeline.birth_year || 1990;
        const gender = timeline.gender || 'male';

        renderLifeTimeline(container, timeline, userEvents, eventMappings, futureWarnings, domains, birthYear);

    } catch (err) {
        container.innerHTML = `<p class="report-placeholder">加载失败: ${err.message}</p>`;
    }
}


export async function renderLifeTimeline(container, timelineData, userEvents, eventMappingsByYear, futureWarnings, domains, birthYear) {
    const dayun = timelineData.dayun || [];
    const liunian = timelineData.liunian || [];

    const currentYear = new Date().getFullYear();
    const minYear = birthYear;
    const maxYear = currentYear + 5;
    const years = [];
    for (let y = minYear; y <= maxYear; y++) years.push(y);

    const liunianMap = {};
    for (const ln of liunian) {
        if (ln.year) liunianMap[ln.year] = ln;
    }

    const domainColors = {
        career: '#4A90D9',
        wealth: '#F5A623',
        relationship: '#E91E8C',
        health: '#27AE60',
        family: '#9B59B6',
        personality: '#1ABC9C',
        study: '#E74C3C',
        annual_fortune: '#7F8C8D',
    };

    const activeDomains = new Set(Object.keys(domainColors));

    const chartDom = document.createElement('div');
    chartDom.style.width = '100%';
    chartDom.style.minHeight = '320px';

    const buttonsHtml = `
        <div class="timeline-domain-filters">
            ${Object.keys(domainColors).map(d =>
                `<button class="domain-toggle active" data-domain="${d}" style="--dom-color:${domainColors[d]}">${d}</button>`
            ).join('')}
            <button class="add-event-btn" id="timeline-add-event-btn">+ 添加事件</button>
        </div>
        <div class="timeline-warnings" id="timeline-warnings"></div>
    `;

    const detailPanel = document.createElement('div');
    detailPanel.className = 'timeline-year-detail';
    detailPanel.style.display = 'none';

    const modal = createAddEventModal(container, timelineData.chart_id, (newEvent) => {
        userEvents.push(newEvent);
        renderYearDetail(detailPanel, detailPanel._currentYear, timelineData, userEvents, eventMappingsByYear, birthYear);
    });

    container.innerHTML = '';
    container.insertAdjacentHTML('beforeend', buttonsHtml);
    container.appendChild(chartDom);
    container.appendChild(detailPanel);

    bindDomainToggles(container, domainColors, activeDomains, chartDom, timelineData, userEvents, eventMappingsByYear, birthYear, liunianMap, years, detailPanel, modal);

    bindAddEventBtn(container, modal, birthYear);

    renderFutureWarnings(container, futureWarnings);

    const echarts = await loadEcharts();
    const myChart = echarts.init(chartDom);
    chartDom._echarts = myChart;
    chartDom._timelineData = timelineData;
    chartDom._userEvents = userEvents;
    chartDom._eventMappings = eventMappingsByYear;
    chartDom._birthYear = birthYear;
    chartDom._liunianMap = liunianMap;
    chartDom._years = years;
    chartDom._detailPanel = detailPanel;
    chartDom._modal = modal;
    chartDom._activeDomains = activeDomains;

    const option = buildKLineOption(timelineData, userEvents, eventMappingsByYear, birthYear, liunianMap, years, activeDomains, domainColors);
    myChart.setOption(option);

    myChart.on('click', (params) => {
        if (params.componentType === 'xAxis' || params.componentType === 'series') {
            let year;
            if (params.componentType === 'xAxis') {
                year = parseInt(params.value);
            } else {
                year = params.data && params.data[0];
            }
            if (year) {
                renderYearDetail(detailPanel, year, timelineData, userEvents, eventMappingsByYear, birthYear);
                detailPanel.style.display = 'block';
            }
        }
    });

    window.addEventListener('resize', () => myChart.resize());
}


function buildKLineOption(timelineData, userEvents, eventMappingsByYear, birthYear, liunianMap, years, activeDomains, domainColors) {
    const dayun = timelineData.dayun || [];

    const liunianScores = years.map(y => {
        const ln = liunianMap[y];
        return ln && ln.score !== undefined ? [y, parseFloat((ln.score).toFixed(3))] : [y, null];
    });

    const liunianBars = years.map(y => {
        const ln = liunianMap[y];
        return ln && ln.score !== undefined ? [y, Math.round(ln.score * 100)] : [y, 0];
    });

    const markAreas = dayun.map(dy => {
        const startYear = birthYear + (dy.age || 0);
        const endYear = birthYear + (dy.end_age || dy.age || 0) + 1;
        const score = dy.score || 0.5;
        const r = Math.floor(200 - score * 100);
        const g = Math.floor(220 - score * 80);
        const b = Math.floor(240 - score * 100);
        return [
            { year: startYear, score: dy.score },
            { year: Math.min(endYear, years[years.length - 1]) + 1, score: dy.score }
        ];
    });

    const userEventScatters = [];
    for (const ev of userEvents) {
        const year = ev.event_year;
        if (!year || !activeDomains.has(ev.domain)) continue;
        userEventScatters.push({
            value: [year, 0.5 + (ev.impact_level || 3) * 0.04],
            symbol: 'star',
            symbolSize: 12,
            itemStyle: { color: domainColors[ev.domain] || '#888', shadowBlur: 6 },
            domain: ev.domain,
            title: ev.title,
            impact_level: ev.impact_level,
        });
    }

    const today = new Date().getFullYear();
    const splitLines = [];
    for (let y = birthYear + 10; y <= today; y += 10) {
        splitLines.push({
            value: y,
            lineStyle: { color: 'rgba(150,150,150,0.3)', type: 'dashed', width: 1 },
            label: { show: true, formatter: y + '年', position: 'end', color: '#999', fontSize: 10 },
        });
    }

    return {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            formatter: function(params) {
                let year = null;
                let score = null;
                let dayunArea = '';
                let html = '';
                for (const p of params) {
                    if (p.seriesName === '流年运势') {
                        year = p.data[0];
                        score = p.data[1];
                    }
                    if (p.seriesName === '大运区间') {
                        dayunArea = `<div style="margin-top:4px;font-size:11px;color:#aaa">大运: ${p.data[2] || ''} 评分: ${p.data[3] || ''}</div>`;
                    }
                }
                if (year === null) return '';
                html = `<strong>${year}年</strong><br/>`;
                if (score !== null) html += `运势评分: ${(score * 100).toFixed(0)}%<br/>`;
                html += dayunArea;
                const evs = userEvents.filter(e => e.event_year === year);
                if (evs.length) {
                    html += '<div style="margin-top:4px;border-top:1px solid #eee;padding-top:4px">';
                    for (const ev of evs) {
                        const color = domainColors[ev.domain] || '#888';
                        html += `<span style="color:${color};font-size:11px">◆</span> ${ev.title} (${ev.domain})<br/>`;
                    }
                    html += '</div>';
                }
                return html;
            },
        },
        legend: { selected: { '用户事件': true, '流年运势': true, '流年柱状': false } },
        grid: { left: 50, right: 20, top: 30, bottom: 40 },
        xAxis: {
            type: 'category',
            data: years,
            boundaryGap: false,
            axisLabel: { fontSize: 10, color: '#666', interval: 1 },
            axisLine: { lineStyle: { color: '#ddd' } },
            splitLine: { show: false },
            axisTick: { alignWithLabel: true },
        },
        yAxis: [
            {
                name: '运势',
                type: 'value',
                min: 0,
                max: 1,
                axisLabel: { formatter: v => (v * 100).toFixed(0) + '%', fontSize: 10, color: '#666' },
                splitLine: { lineStyle: { color: '#f0f0f0' } },
            },
            {
                name: '强度',
                type: 'value',
                min: 0,
                max: 100,
                axisLabel: { fontSize: 10, color: '#666' },
                splitLine: { show: false },
            },
        ],
        series: [
            {
                name: '大运区间',
                type: 'line',
                xAxisIndex: 0,
                yAxisIndex: 0,
                data: years.map(y => {
                    let dyScore = 0.5;
                    for (const dy of dayun) {
                        const startAge = dy.age || 0;
                        const endAge = dy.end_age || dy.age || 0;
                        const age = y - birthYear;
                        if (age >= startAge && age <= endAge) {
                            dyScore = dy.score || 0.5;
                            break;
                        }
                    }
                    return [y, dyScore, '', ''];
                }),
                lineStyle: { width: 0 },
                symbol: 'none',
                itemStyle: { opacity: 0 },
                markArea: {
                    silent: true,
                    data: dayun.map(dy => {
                        const startYear = birthYear + (dy.age || 0);
                        const endYear = Math.min(birthYear + (dy.end_age || dy.age || 0) + 1, years[years.length - 1]);
                        const r = Math.floor(200 - (dy.score || 0.5) * 100);
                        const g = Math.floor(220 - (dy.score || 0.5) * 80);
                        const b = Math.floor(240 - (dy.score || 0.5) * 100);
                        return [
                            {
                                year: startYear,
                                itemStyle: { color: `rgba(${r},${g},${b},0.12)`, borderWidth: 0 },
                                label: { show: true, position: 'insideTop', formatter: `${dy.gan_zhi || ''}`, fontSize: 9, color: '#888' },
                            },
                            { year: endYear },
                        ];
                    }),
                },
            },
            {
                name: '流年运势',
                type: 'line',
                xAxisIndex: 0,
                yAxisIndex: 0,
                data: liunianScores,
                smooth: 0.3,
                lineStyle: { color: '#4A90D9', width: 2 },
                itemStyle: { color: '#4A90D9' },
                areaStyle: { color: 'rgba(74,144,217,0.08)' },
                connectNulls: true,
            },
            {
                name: '流年柱状',
                type: 'bar',
                xAxisIndex: 0,
                yAxisIndex: 1,
                data: liunianBars,
                barWidth: '60%',
                itemStyle: { color: 'rgba(74,144,217,0.25)' },
            },
            {
                name: '用户事件',
                type: 'scatter',
                xAxisIndex: 0,
                yAxisIndex: 0,
                data: userEvents
                    .filter(ev => ev.event_year && activeDomains.has(ev.domain))
                    .map(ev => ({
                        value: [ev.event_year, 0.5 + (ev.impact_level || 3) * 0.04],
                        symbol: 'circle',
                        symbolSize: 14,
                        itemStyle: {
                            color: domainColors[ev.domain] || '#888',
                            borderColor: '#fff',
                            borderWidth: 2,
                            shadowBlur: 4,
                        },
                        title: ev.title,
                        domain: ev.domain,
                    })),
                label: { show: false },
            },
        ],
    };
}


function renderYearDetail(panel, year, timelineData, userEvents, eventMappingsByYear, birthYear) {
    const liunian = timelineData.liunian || [];
    const ln = liunian.find(l => l.year === year) || {};
    const age = year - birthYear;
    const mappings = eventMappingsByYear[year] || [];
    const evs = userEvents.filter(e => e.event_year === year);

    const warnings = (timelineData.future_warnings || []).filter(w => w.year === year);

    let html = `<div class="year-detail-header">
        <strong>${year}年</strong> <span style="color:#999;font-size:12px">（年龄 ${age}岁）</span>
        <span style="float:right;color:#666;font-size:12px">${ln.gan_zhi || ''} · 评分 ${ln.score ? (ln.score * 100).toFixed(0) + '%' : 'N/A'}</span>
    </div>`;

    if (mappings.length) {
        html += '<div class="year-detail-section"><strong>命理分析</strong>';
        for (const m of mappings) {
            html += `<div class="em-item">${m.domain ? `<span class="em-domain">${m.domain}</span>` : ''}${m.tendency || m.event || ''} <span style="color:#999;font-size:11px">置信:${m.confidence ? (m.confidence * 100).toFixed(0) + '%' : 'N/A'}</span></div>`;
        }
        html += '</div>';
    }

    if (evs.length) {
        html += '<div class="year-detail-section"><strong>真实事件</strong>';
        for (const ev of evs) {
            html += `<div class="ev-item"><span class="ev-domain">${ev.domain}</span>${ev.title} <span style="color:#999;font-size:11px">影响${ev.impact_level}级</span></div>`;
        }
        html += '</div>';
    }

    if (warnings.length) {
        html += '<div class="year-detail-section"><strong>关键提示</strong>';
        for (const w of warnings) {
            html += `<div class="warning-item urgency-${w.urgency || 'low'}">${w.message}</div>`;
        }
        html += '</div>';
    }

    panel.innerHTML = html;
    panel._currentYear = year;
}


function bindDomainToggles(container, domainColors, activeDomains, chartDom, timelineData, userEvents, eventMappingsByYear, birthYear, liunianMap, years, detailPanel, modal) {
    container.querySelectorAll('.domain-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
            const d = btn.dataset.domain;
            if (activeDomains.has(d)) {
                activeDomains.delete(d);
                btn.classList.remove('active');
            } else {
                activeDomains.add(d);
                btn.classList.add('active');
            }
            const myChart = chartDom._echarts;
            if (!myChart) return;
            const option = buildKLineOption(
                timelineData, userEvents, eventMappingsByYear,
                birthYear, liunianMap, years, activeDomains, domainColors
            );
            myChart.setOption(option, true);
        });
    });
}


function bindAddEventBtn(container, modal, birthYear) {
    const btn = document.getElementById('timeline-add-event-btn');
    if (btn) {
        btn.addEventListener('click', () => {
            modal.show(birthYear);
        });
    }
}


function createAddEventModal(container, chartId, onSuccess) {
    let modalEl = null;

    function buildModal() {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal-content">
                <h3>添加人生事件</h3>
                <form id="add-event-form">
                    <div class="form-group">
                        <label>年份</label>
                        <input type="number" id="ev-year" min="1900" max="2100" placeholder="如 2020" required>
                    </div>
                    <div class="form-group">
                        <label>领域</label>
                        <select id="ev-domain">
                            <option value="career">事业</option>
                            <option value="wealth">财运</option>
                            <option value="relationship">感情</option>
                            <option value="health">健康</option>
                            <option value="family">家庭</option>
                            <option value="personality">性格</option>
                            <option value="study">学业</option>
                            <option value="annual_fortune">年运</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>标题</label>
                        <input type="text" id="ev-title" maxlength="100" placeholder="事件标题" required>
                    </div>
                    <div class="form-group">
                        <label>描述</label>
                        <textarea id="ev-desc" rows="3" placeholder="详细描述（可选）"></textarea>
                    </div>
                    <div class="form-group">
                        <label>影响等级（1-5）</label>
                        <input type="number" id="ev-impact" min="1" max="5" value="3">
                    </div>
                    <div class="modal-actions">
                        <button type="submit" class="btn-primary">保存</button>
                        <button type="button" class="btn-cancel">取消</button>
                    </div>
                </form>
            </div>`;

        document.body.appendChild(overlay);
        modalEl = overlay;

        overlay.querySelector('.btn-cancel').addEventListener('click', () => hide());
        overlay.addEventListener('click', (e) => { if (e.target === overlay) hide(); });

        overlay.querySelector('#add-event-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const payload = {
                event_year: parseInt(overlay.querySelector('#ev-year').value),
                domain: overlay.querySelector('#ev-domain').value,
                title: overlay.querySelector('#ev-title').value,
                description: overlay.querySelector('#ev-desc').value,
                impact_level: parseInt(overlay.querySelector('#ev-impact').value),
                source: 'user',
            };

            try {
                const resp = await fetch(`${API}/charts/${chartId}/life-events`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!resp.ok) throw new Error('Save failed');
                const saved = await resp.json();
                hide();
                onSuccess(saved);
            } catch (err) {
                alert('保存失败: ' + err.message);
            }
        });

        return overlay;
    }

    function show(suggestedYear) {
        if (!modalEl) buildModal();
        const now = new Date().getFullYear();
        modalEl.querySelector('#ev-year').value = suggestedYear || now;
        modalEl.style.display = 'flex';
    }

    function hide() {
        if (modalEl) modalEl.style.display = 'none';
    }

    return { show, hide };
}


function renderFutureWarnings(container, warnings) {
    const el = document.getElementById('timeline-warnings');
    if (!el || !warnings.length) return;

    const next5 = warnings.filter(w => {
        const now = new Date().getFullYear();
        return w.year >= now && w.year <= now + 5;
    }).slice(0, 5);

    if (!next5.length) return;

    el.innerHTML = `<div class="warnings-title">未来5年关键节点</div>
        ${next5.map(w => `
            <div class="warning-badge urgency-${w.urgency || 'low'}">
                <span class="warning-year">${w.year}年</span>
                <span class="warning-msg">${w.message}</span>
            </div>
        `).join('')}`;
}


let _echarts = null;
async function loadEcharts() {
    if (_echarts) return _echarts;
    await new Promise((resolve, reject) => {
        if (window.echarts) { _echarts = window.echarts; resolve(); return; }
        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js';
        s.onload = () => { _echarts = window.echarts; resolve(); };
        s.onerror = reject;
        document.head.appendChild(s);
    });
    return _echarts;
}

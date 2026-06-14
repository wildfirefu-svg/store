// ================================================================
// 玄机子 Frontend — 八字命盘渲染
// ================================================================

export function renderBaziTable(chart) {
    if (!chart || !chart.four_pillars) { document.getElementById('bazi-table').innerHTML = '<p style="color:var(--coral);text-align:center;padding:8px">八字数据缺失</p>'; return; }
    const fp = chart.four_pillars, dm = chart.day_master, ws = chart.wuxing_stats;
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
    h += '<div class="pillars-row">';
    for (let i = 0; i < cols.length; i++) {
        const k = cols[i], p = fp[k];
        const cg = p.cang_gan || [], css = p.cang_gan_shi_shen || [];
        const sha = shenshaMap[k] || [];
        const isDay = k === 'day';

        h += '<div class="pillar">';
        h += '<div class="pillar-label">' + colLabels[i] + '</div>';
        h += '<div class="pillar-shishen">' + (isDay ? '日主' : (p.shi_shen_gan || '—')) + '</div>';
        h += '<div class="pillar-gan">' + wxSpan(p.gan, p.gan_wuxing || '') + '</div>';
        h += '<div class="pillar-zhi">' + wxSpan(p.zhi, p.zhi_wuxing || '') + '</div>';
        h += '<div class="pillar-canggan">';
        for (let j = 0; j < Math.max(cg.length, 1); j++) {
            const s = cg[j] || '—';
            const sss = css[j] || '';
            h += '<span class="cgl">' + s + (sss ? ' <span class="cgss">' + sss + '</span>' : '') + '</span>';
        }
        h += '</div>';
        h += '<div class="pillar-nayin">' + (p.nayin || '—') + '</div>';
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

    h += '</div>';
    document.getElementById('bazi-table').innerHTML = h;
    document.getElementById('bazi-summary').innerHTML = '';
}

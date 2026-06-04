// ================================================================
// 玄机子 Frontend — 紫微斗数渲染
// ================================================================

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

    function briClass(b) {
        return 'bri-' + ({'庙':'miao','旺':'wang','得':'de','平':'ping','陷':'xian'}[b] || 'none');
    }
    function briDot(b) {
        return '<span class="bri-dot ' + ({'庙':'miao','旺':'wang','得':'de','平':'ping','陷':'xian'}[b] || 'none') + '">●</span>';
    }

    const sihuaMap = {};
    sihua.forEach(sh => { if (!sh || !sh.star) return; if (!sihuaMap[sh.star]) sihuaMap[sh.star] = []; sihuaMap[sh.star].push(sh.type || ''); });

    const ZHI_GRID = {
        '巳':{row:1,col:1}, '午':{row:1,col:2}, '未':{row:1,col:3}, '申':{row:1,col:4},
        '辰':{row:2,col:1}, '酉':{row:2,col:4},
        '卯':{row:3,col:1}, '戌':{row:3,col:4},
        '寅':{row:4,col:1}, '丑':{row:4,col:2}, '子':{row:4,col:3}, '亥':{row:4,col:4}
    };

    const SHI_CHEN = {
        '子':'子时 (23:00–01:00)','丑':'丑时 (01:00–03:00)','寅':'寅时 (03:00–05:00)',
        '卯':'卯时 (05:00–07:00)','辰':'辰时 (07:00–09:00)','巳':'巳时 (09:00–11:00)',
        '午':'午时 (11:00–13:00)','未':'未时 (13:00–15:00)','申':'申时 (15:00–17:00)',
        '酉':'酉时 (17:00–19:00)','戌':'戌时 (19:00–21:00)','亥':'亥时 (21:00–23:00)'
    };

    const byZhi = {};
    palaces.forEach(p => { byZhi[p.position] = p; });

    function renderStar(sd) {
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
    h += '</div>';

    if (sihua.length > 0) {
        h += '<div class="zw-sihua-bar">';
        sihua.forEach(sh => {
            const s = sh.type || '';
            h += '<span class="sihua-item"><span class="sihua-tag ' + (s === '化禄' ? 'lu' : s === '化权' ? 'quan' : s === '化科' ? 'ke' : 'ji') + '">' + s + '</span> → ' + (sh.star || '') + '</span>';
        });
        h += '</div>';
    }

    h += '<div class="zw-legend">';
    h += '<span class="leg-item"><span class="bri-dot xian">●</span> 陷</span>';
    h += '<span class="leg-item"><span class="bri-dot ping">●</span> 平</span>';
    h += '<span class="leg-item"><span class="bri-dot de">●</span> 得</span>';
    h += '<span class="leg-item"><span class="bri-dot wang">●</span> 旺</span>';
    h += '<span class="leg-item"><span class="bri-dot miao">●</span> 庙</span>';
    h += '</div>';
    h += '</div>';
    el.innerHTML = h;
}

function renderFullChart(chart) {
    try { renderBazi(chart); } catch(e) { console.error('renderBazi error:', e); document.getElementById('bazi-table').innerHTML = '<p style="color:red">八字渲染错误: ' + e.message + '</p>'; }
    try { renderZiwei(chart); } catch(e) { console.error('renderZiwei error:', e); document.getElementById('ziwei-table').innerHTML = '<p style="color:red">紫微渲染错误: ' + e.message + '</p>'; }
}

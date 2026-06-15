const canvas = document.getElementById('card-canvas');
const ctx = canvas.getContext('2d');
const fields = ['teacher-name', 'teacher-contact', 'brand-slogan'];

function loadBrand() {
    fields.forEach((id) => {
        const el = document.getElementById(id);
        el.value = localStorage.getItem(`bazi_${id}`) || '';
        el.addEventListener('input', () => localStorage.setItem(`bazi_${id}`, el.value));
    });
}

async function loadChart(chartId) {
    const response = await fetch(`/api/charts/${encodeURIComponent(chartId)}/data`);
    if (!response.ok) throw new Error('命盘不存在');
    const data = await response.json();
    return data.chart_data || data;
}

function drawCard(chart) {
    const teacher = document.getElementById('teacher-name').value || '玄机子命理师';
    const contact = document.getElementById('teacher-contact').value || '';
    const slogan = document.getElementById('brand-slogan').value || '以命理为镜，见趋势与选择';
    ctx.fillStyle = '#f7efe1';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#3b2618';
    ctx.font = 'bold 44px serif';
    ctx.fillText('玄机子命理卡片', 72, 92);
    ctx.strokeStyle = '#8c6239';
    ctx.lineWidth = 2;
    ctx.strokeRect(48, 48, canvas.width - 96, canvas.height - 96);

    const fp = chart.four_pillars || {};
    const dm = chart.day_master || {};
    const pillars = ['year', 'month', 'day', 'hour'].map((key) => {
        const p = fp[key] || {};
        return `${p.gan || ''}${p.zhi || ''}`;
    }).join('  ');

    ctx.font = '30px serif';
    ctx.fillText(`八字：${pillars}`, 72, 180);
    ctx.fillText(`日主：${dm.gan || ''}${dm.wuxing || ''}${dm.yinyang || ''}`, 72, 236);

    const ws = chart.wuxing_stats || {};
    const names = ['金', '木', '水', '火', '土'];
    ctx.font = '24px sans-serif';
    names.forEach((name, idx) => {
        const value = Number(ws[name] || ws[toKey(name)] || 0);
        const x = 72;
        const y = 320 + idx * 54;
        ctx.fillStyle = '#3b2618';
        ctx.fillText(name, x, y);
        ctx.fillStyle = '#8c6239';
        ctx.fillRect(x + 52, y - 22, Math.max(8, value * 36), 24);
        ctx.fillStyle = '#3b2618';
        ctx.fillText(String(value), x + 260, y);
    });

    ctx.font = '28px serif';
    ctx.fillText('核心提示', 72, 640);
    ctx.font = '24px sans-serif';
    wrapText('具体判断仍需结合时辰准确性、大运流年和现实处境综合参考。', 72, 692, 600, 38);

    ctx.font = '24px sans-serif';
    ctx.fillText(`命理师：${teacher}`, 72, 860);
    if (contact) ctx.fillText(`联系：${contact}`, 72, 902);
    ctx.fillStyle = '#8c6239';
    ctx.fillText(slogan, 72, 944);
}

function wrapText(text, x, y, maxWidth, lineHeight) {
    let line = '';
    for (const ch of text) {
        const testLine = line + ch;
        if (ctx.measureText(testLine).width > maxWidth && line) {
            ctx.fillText(line, x, y);
            line = ch;
            y += lineHeight;
        } else {
            line = testLine;
        }
    }
    if (line) ctx.fillText(line, x, y);
}

function toKey(name) {
    return { '金': 'jin', '木': 'mu', '水': 'shui', '火': 'huo', '土': 'tu' }[name] || name;
}

document.getElementById('generate-card').addEventListener('click', async () => {
    const status = document.getElementById('status');
    try {
        status.textContent = '生成中...';
        const chartId = document.getElementById('chart-id').value.trim();
        const chart = await loadChart(chartId);
        drawCard(chart);
        status.textContent = '已生成';
    } catch (err) {
        status.textContent = err.message;
    }
});

document.getElementById('download-card').addEventListener('click', () => {
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = 'bazi-card.png';
    a.click();
});

loadBrand();

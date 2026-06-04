// Tools page logic — API constant from api.js
const chartId = sessionStorage.getItem('chartId') || '';
if (chartId) {
    document.getElementById('zeri-chart-id').value = chartId;
    document.getElementById('liunian-chart-id').value = chartId;
    document.getElementById('name-chart-id').value = chartId;
}

// Zeri
document.getElementById('zeri-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const result = document.getElementById('zeri-result');
    result.innerHTML = '<span class="loading"></span>查找中...';
    try {
        const r = await fetch(`${API}/tools/zeri`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                chart_id: document.getElementById('zeri-chart-id').value,
                year: parseInt(document.getElementById('zeri-year').value),
                month: parseInt(document.getElementById('zeri-month').value),
                purpose: document.getElementById('zeri-purpose').value,
                top_n: 5
            })
        });
        const data = await r.json();
        let html = '<table><tr><th>日期</th><th>建除</th><th>干支</th><th>评分</th><th>要点</th></tr>';
        data.dates.forEach(d => {
            html += `<tr><td>${d.date} ${d.weekday}</td><td>${d.ri_chen}日</td>`;
            html += `<td>${d.ri_ganzhi}</td><td><b>${d.score}</b></td>`;
            html += `<td>${(d.detail||[]).slice(0,3).join('；')}</td></tr>`;
        });
        html += '</table>';
        result.innerHTML = html;
    } catch (err) {
        result.innerHTML = `<span class="bad">错误: ${err.message}</span>`;
    }
});

// Liunian
document.getElementById('liunian-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const result = document.getElementById('liunian-result');
    result.innerHTML = '<span class="loading"></span>生成中...';
    try {
        const r = await fetch(`${API}/tools/liunian`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                chart_id: document.getElementById('liunian-chart-id').value,
                target_year: parseInt(document.getElementById('liunian-year').value)
            })
        });
        const data = await r.json();
        let html = `<p><b>${data.liunian_ganzhi}年</b> · ${data.liunian_shishen} · `;
        html += `最佳月: ${data.overview.best_month.month}月(${data.overview.best_month.rating}) · `;
        html += `需注意: ${data.overview.worst_month.month}月(${data.overview.worst_month.rating})</p>`;
        html += '<table><tr><th>月</th><th>干支</th><th>十神</th><th>评分</th><th>事业</th><th>财运</th><th>感情</th><th>健康</th></tr>';
        data.months.forEach(m => {
            const stars = '★'.repeat(m.rating_stars) + '☆'.repeat(5-m.rating_stars);
            html += `<tr><td>${m.month}</td><td>${m.ganzhi}</td><td>${m.shishen}</td>`;
            html += `<td>${stars}</td><td>${m.career.score}</td><td>${m.wealth.score}</td>`;
            html += `<td>${m.love.score}</td><td>${m.health.score}</td></tr>`;
        });
        html += '</table>';
        result.innerHTML = html;
    } catch (err) {
        result.innerHTML = `<span class="bad">需要先排盘。请回到首页输入出生信息。</span>`;
    }
});

// Name eval
document.getElementById('name-eval-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const result = document.getElementById('name-result');
    result.innerHTML = '<span class="loading"></span>评测中...';
    try {
        const r = await fetch(`${API}/tools/name/eval`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                chart_id: document.getElementById('name-chart-id').value,
                name: document.getElementById('eval-name').value,
                gender: 'male'
            })
        });
        const data = await r.json();
        let html = `<h3>${data.name} · ${data.total_score}分 · ${data.grade}</h3>`;
        html += '<table><tr><th>维度</th><th>得分</th><th>说明</th></tr>';
        for (const [dim, s] of Object.entries(data.scores)) {
            html += `<tr><td>${dim}</td><td>${s.score}/${s.max}</td><td>${s.detail||''}</td></tr>`;
        }
        html += '</table>';
        html += `<p><b>${data.verdict}</b></p>`;
        result.innerHTML = html;
    } catch (err) {
        result.innerHTML = `<span class="bad">错误: ${err.message}</span>`;
    }
});

// Name gen
document.getElementById('name-gen-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const result = document.getElementById('name-result');
    result.innerHTML = '<span class="loading"></span>生成中...';
    try {
        const r = await fetch(`${API}/tools/name/gen`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                chart_id: document.getElementById('name-chart-id').value,
                surname: document.getElementById('gen-surname').value || '张',
                gender: document.getElementById('gen-gender').value,
                top_n: 5
            })
        });
        const data = await r.json();
        let html = '<table><tr><th>#</th><th>姓名</th><th>评分</th><th>评级</th><th>策略</th></tr>';
        data.forEach((n, i) => {
            html += `<tr><td>${i+1}</td><td><b>${n.name}</b></td><td>${n.total_score}</td>`;
            html += `<td>${n.grade}</td><td>${n.strategy}</td></tr>`;
        });
        html += '</table>';
        result.innerHTML = html;
    } catch (err) {
        result.innerHTML = `<span class="bad">错误: ${err.message}</span>`;
    }
});

function switchNameTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('name-eval-form').classList.toggle('hidden', tab !== 'eval');
    document.getElementById('name-gen-form').classList.toggle('hidden', tab !== 'gen');
    document.getElementById('name-result').innerHTML = '';
}

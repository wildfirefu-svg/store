const els = {
    runs: document.getElementById('run-list'),
    report: document.getElementById('report-preview'),
    weakDomains: document.getElementById('weak-domains'),
    accuracy: document.getElementById('metric-accuracy'),
    evidence: document.getElementById('metric-evidence'),
    stability: document.getElementById('metric-stability'),
    safety: document.getElementById('metric-safety'),
};

function pct(value) {
    if (value === null || value === undefined || value === '') return '--';
    return `${Math.round(Number(value) * 100)}%`;
}

function renderCards(run) {
    if (!run) return;
    els.accuracy.textContent = pct(run.accuracy);
    els.evidence.textContent = pct(run.evidence_score);
    els.stability.textContent = pct(run.stability_score);
    els.safety.textContent = pct(run.safety_score);
}

function runMeta(run) {
    const model = [run.provider, run.model].filter(Boolean).join(' / ') || 'unknown model';
    const prompt = [run.prompt_version, run.reasoning_protocol].filter(Boolean).join(' / ') || 'unknown prompt';
    return `${model}<br>${prompt}<br>${run.n_cases || 0} cases · ${run.created_at || ''}`;
}

function renderRunList(runs) {
    if (!runs.length) {
        els.runs.innerHTML = '<div class="empty-state">暂无 benchmark run</div>';
        return;
    }
    els.runs.innerHTML = '';
    for (const run of runs) {
        const item = document.createElement('div');
        item.className = 'run-item';
        item.dataset.runId = run.id;
        item.innerHTML = `
            <div class="run-id">${run.id}</div>
            <div class="run-meta">${runMeta(run)}</div>
            <div class="run-meta">Accuracy ${pct(run.accuracy)} · Evidence ${pct(run.evidence_score)} · Safety ${pct(run.safety_score)}</div>
        `;
        item.addEventListener('click', () => {
            document.querySelectorAll('.run-item').forEach(x => x.classList.remove('active'));
            item.classList.add('active');
            renderCards(run);
            loadReport(run.id);
        });
        els.runs.appendChild(item);
    }
    const first = els.runs.querySelector('.run-item');
    if (first) first.click();
}

function renderWeakDomains(text) {
    const lines = text.split('\n').filter(line => line.includes('← 需关注') || line.includes('领域短板'));
    els.weakDomains.textContent = lines.length ? lines.join('\n') : '';
}

async function loadReport(runId) {
    els.report.textContent = '加载报告中...';
    try {
        const resp = await fetch(`/api/benchmark/report/${runId}`);
        if (!resp.ok) {
            els.report.textContent = `报告不可用：HTTP ${resp.status}`;
            els.weakDomains.textContent = '';
            return;
        }
        const text = await resp.text();
        els.report.textContent = text;
        renderWeakDomains(text);
    } catch (err) {
        els.report.textContent = `报告加载失败：${err.message}`;
    }
}

async function loadRuns() {
    try {
        const resp = await fetch('/api/benchmark/runs');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const runs = await resp.json();
        renderCards(runs[0]);
        renderRunList(runs);
    } catch (err) {
        els.runs.innerHTML = `<div class="empty-state">加载失败：${err.message}</div>`;
    }
}

loadRuns();

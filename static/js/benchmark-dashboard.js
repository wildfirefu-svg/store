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
    const n = Number(value);
    return Number.isFinite(n) ? `${Math.round(n * 100)}%` : '--';
}

function text(value) {
    if (value === null || value === undefined) return '';
    return String(value);
}

function setEmptyState(message) {
    els.runs.textContent = '';
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = message;
    els.runs.appendChild(empty);
}

function renderCards(run) {
    if (!run) return;
    els.accuracy.textContent = pct(run.accuracy);
    els.evidence.textContent = pct(run.evidence_score);
    els.stability.textContent = pct(run.stability_score);
    els.safety.textContent = pct(run.safety_score);
}

function appendLine(parent, value) {
    if (parent.childNodes.length) parent.appendChild(document.createElement('br'));
    parent.appendChild(document.createTextNode(text(value)));
}

function buildRunItem(run) {
    const item = document.createElement('div');
    item.className = 'run-item';
    item.dataset.runId = text(run.id);

    const idEl = document.createElement('div');
    idEl.className = 'run-id';
    idEl.textContent = text(run.id);
    item.appendChild(idEl);

    const metaEl = document.createElement('div');
    metaEl.className = 'run-meta';
    appendLine(metaEl, [run.provider, run.model].filter(Boolean).join(' / ') || 'unknown model');
    appendLine(metaEl, [run.prompt_version, run.reasoning_protocol].filter(Boolean).join(' / ') || 'unknown prompt');
    appendLine(metaEl, `${run.n_cases || 0} cases · ${text(run.created_at)}`);
    item.appendChild(metaEl);

    const scoreEl = document.createElement('div');
    scoreEl.className = 'run-meta';
    scoreEl.textContent = `Accuracy ${pct(run.accuracy)} · Evidence ${pct(run.evidence_score)} · Safety ${pct(run.safety_score)}`;
    item.appendChild(scoreEl);

    item.addEventListener('click', () => {
        document.querySelectorAll('.run-item').forEach(x => x.classList.remove('active'));
        item.classList.add('active');
        renderCards(run);
        loadReport(run.id);
    });
    return item;
}

function renderRunList(runs) {
    if (!runs.length) {
        setEmptyState('暂无 benchmark run');
        return;
    }
    els.runs.textContent = '';
    for (const run of runs) {
        els.runs.appendChild(buildRunItem(run));
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
        const resp = await fetch(`/api/benchmark/report/${encodeURIComponent(runId)}`);
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
        setEmptyState(`加载失败：${err.message}`);
    }
}

loadRuns();

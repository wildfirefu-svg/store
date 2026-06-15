import { renderFeedbackControls } from './feedback.js';

export function renderTimeline(container, analyses, onFeedbackSubmitted) {
    container.innerHTML = '';
    if (!analyses || analyses.length === 0) {
        container.innerHTML = '<div class="empty">暂无分析记录</div>';
        return;
    }
    analyses.forEach((analysis) => {
        const item = document.createElement('article');
        item.className = 'timeline-item';
        item.innerHTML = `
            <div class="timeline-meta">${escapeHtml(analysis.created_at || '')} · ${escapeHtml(analysis.topic || '')}</div>
            <h3>${escapeHtml(analysis.question || '未命名分析')}</h3>
            <pre>${escapeHtml((analysis.ai_text || '').slice(0, 600))}</pre>
        `;
        item.appendChild(renderFeedbackControls(analysis, onFeedbackSubmitted));
        container.appendChild(item);
    });
}

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }[ch]));
}

import { submitFeedback } from './client-api.js';

export function renderFeedbackControls(analysis, onSubmitted) {
    const wrap = document.createElement('div');
    wrap.className = 'feedback-controls';
    wrap.innerHTML = `
        <select class="feedback-dimension">
            <option value="overall">整体</option>
            <option value="career">事业</option>
            <option value="wealth">财运</option>
            <option value="marriage">婚姻</option>
            <option value="health">健康</option>
        </select>
        <input class="feedback-judgment" placeholder="反馈对应断语" value="${escapeHtml((analysis.ai_text || '').slice(0, 40))}">
        <input class="feedback-comment" placeholder="备注">
        <button data-accurate="1">准</button>
        <button data-accurate="0">不准</button>
        <span class="feedback-status"></span>
    `;
    wrap.querySelectorAll('button[data-accurate]').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const status = wrap.querySelector('.feedback-status');
            status.textContent = '提交中...';
            try {
                await submitFeedback(analysis.id, {
                    dimension: wrap.querySelector('.feedback-dimension').value,
                    judgment_text: wrap.querySelector('.feedback-judgment').value || analysis.question || '未填写断语',
                    is_accurate: btn.dataset.accurate === '1',
                    user_comment: wrap.querySelector('.feedback-comment').value || '',
                });
                status.textContent = '已记录';
                if (onSubmitted) onSubmitted();
            } catch (err) {
                status.textContent = err.message;
            }
        });
    });
    return wrap;
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

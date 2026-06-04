// ================================================================
// 玄机子 Frontend — API 通信层
// ================================================================
const API = '/api';

async function apiCreateChart(birth) {
    const r = await fetch(API + '/chart', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(birth) });
    return r.ok ? r.json() : null;
}

// Dead code — never called, kept for reference. Remove after verifying no external callers.
// async function apiGenerateReport(chartId, mode) {
//     const r = await fetch(API + '/analyze', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({chart_id:chartId, mode:mode}) });
//     return r.ok ? (await r.json()).report : null;
// }

function apiChatStream(chartId, message, onReplyDelta, onReportDelta, onToolStart, onDone) {
    var params = new URLSearchParams({chart_id: chartId, message: message});
    var url = '/api/chat/stream?' + params;
    var gotContent = false;
    var aborted = false;
    var reader = null;

    var ctrl = new AbortController();

    fetch(url, {signal: ctrl.signal}).then(function(response) {
        if (!response.ok) {
            throw new Error('HTTP ' + response.status);
        }
        reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';

        function pump() {
            if (aborted) return;
            return reader.read().then(function(result) {
                if (result.done) {
                    if (!gotContent) {
                        onReplyDelta('\n\n⚠️ AI 服务连接失败。请确认：\n1. 已设置 DEEPSEEK_API_KEY，或在项目目录创建 .deepseek_key / .anthropic_key 文件\n2. API Key 有效且账户余额/额度可用\n3. 当前启动后端的终端可以访问 DeepSeek/Anthropic API', null);
                    }
                    onDone(0);
                    return;
                }
                buffer += decoder.decode(result.value, {stream: true});
                var lines = buffer.split('\n');
                buffer = lines.pop();
                var eventType = '';
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];
                    if (line.indexOf('event: ') === 0) {
                        eventType = line.slice(7).trim();
                    } else if (line.indexOf('data: ') === 0) {
                        var dataStr = line.slice(6);
                        try {
                            var data = JSON.parse(dataStr);
                            if (eventType === 'tool') {
                                gotContent = true;
                                onToolStart(data.name);
                            } else if (eventType === 'reply') {
                                gotContent = true;
                                onReplyDelta(data.text, data.tool || null);
                            } else if (eventType === 'report') {
                                gotContent = true;
                                onReportDelta(data.text, data.tab || 'overview');
                            } else if (eventType === 'done') {
                                onDone(data.corrections || 0);
                                aborted = true;
                                if (reader) { try { reader.cancel(); } catch(e) {} }
                                return;
                            }
                        } catch(e) { /* skip malformed JSON */ }
                    }
                }
                return pump();
            }).catch(function(e) {
                if (!gotContent) {
                    var detail = (e && e.message) ? e.message : String(e || '');
                    onReplyDelta('\n\n⚠️ AI 服务连接失败（' + detail + '）。\n请确认：\n1. 已设置 DEEPSEEK_API_KEY，或在项目目录创建 .deepseek_key / .anthropic_key 文件\n2. API Key 有效且账户余额/额度可用\n3. 当前启动后端的终端可以访问 DeepSeek/Anthropic API', null);
                }
                onDone(0);
            });
        }
        return pump();
    }).catch(function(e) {
        if (!gotContent) {
            var detail = (e && e.message) ? e.message : String(e || '');
            onReplyDelta('\n\n⚠️ AI 服务连接失败（' + detail + '）。\n请确认：\n1. 已设置 DEEPSEEK_API_KEY，或在项目目录创建 .deepseek_key / .anthropic_key 文件\n2. API Key 有效且账户余额/额度可用\n3. 当前启动后端的终端可以访问 DeepSeek/Anthropic API', null);
        }
        onDone(0);
    });
}

// ================================================================
// 玄机子 Frontend — API 通信层
// ================================================================
export const API = '/api';

export async function apiCreateChart(birth) {
    const r = await fetch(API + '/chart', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(birth) });
    return r.ok ? r.json() : null;
}


export function apiChatStream(chartId, message, onReplyDelta, onReportDelta, onToolStart, onDone, options) {
    var params = new URLSearchParams({chart_id: chartId, message: message});
    options = options || {};
    if (options.reasoning_mode) params.set('reasoning_mode', options.reasoning_mode);
    if (options.memory_mode) params.set('memory_mode', options.memory_mode);
    var url = '/api/chat/stream?' + params;
    var gotContent = false;
    var aborted = false;
    var reader = null;

    var ctrl = new AbortController();

    function dispatchEvent(eventType, dataLines) {
        if (!eventType || !dataLines.length) return;
        var dataStr = dataLines.join('\n');
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
                gotContent = true;
                onDone(data.corrections || 0);
                aborted = true;
                if (reader) { try { reader.cancel(); } catch(e) {} }
            }
        } catch(e) {}
    }

    fetch(url, {signal: ctrl.signal}).then(function(response) {
        if (!response.ok) {
            throw new Error('HTTP ' + response.status);
        }
        reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';
        var currentEventType = '';
        var currentDataLines = [];

        function pump() {
            if (aborted) return;
            return reader.read().then(function(result) {
                if (result.done) {
                    if (buffer) {
                        var remaining = buffer.split(/\r?\n/);
                        buffer = '';
                        for (var r = 0; r < remaining.length; r++) {
                            var rem = remaining[r];
                            if (rem.indexOf('event:') === 0) currentEventType = rem.slice(6).trim();
                            else if (rem.indexOf('data:') === 0) currentDataLines.push(rem.slice(5).trimStart());
                        }
                        dispatchEvent(currentEventType, currentDataLines);
                    }
                    if (!gotContent) {
                        onReplyDelta('\n\n⚠️ AI 服务连接失败。请确认：\n1. 已设置 DEEPSEEK_API_KEY，或在项目目录创建 .deepseek_key / .anthropic_key 文件\n2. API Key 有效且账户余额/额度可用\n3. 当前启动后端的终端可以访问 DeepSeek/Anthropic API', null);
                    }
                    onDone(0);
                    return;
                }
                buffer += decoder.decode(result.value, {stream: true});
                var lines = buffer.split(/\r?\n/);
                buffer = lines.pop();
                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];
                    if (line === '') {
                        dispatchEvent(currentEventType, currentDataLines);
                        currentEventType = '';
                        currentDataLines = [];
                        if (aborted) return;
                    } else if (line.indexOf('event:') === 0) {
                        currentEventType = line.slice(6).trim();
                    } else if (line.indexOf('data:') === 0) {
                        currentDataLines.push(line.slice(5).trimStart());
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

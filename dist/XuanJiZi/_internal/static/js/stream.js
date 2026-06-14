// ================================================================
// 玄机子 Frontend — 流式报告 + 工具条
// ================================================================

import { apiChatStream } from './api.js';
import { ChatHistory, CorrectionManager, MingzhuManager, PersistenceSync } from './state.js';
import { renderMarkdown } from './markdown.js';
import { addChatMsg, ReportTabs } from './ui.js';

export function showReport(content) {
    document.getElementById('report-content').innerHTML = renderMarkdown(content);
}

export function _sendWithStream(chartId, prompt, onSuccess, forceTab) {
    document.getElementById('report-status').classList.remove('done');
    document.getElementById('report-content').innerHTML =
        '<div class="report-loading"><div class="skeleton-line"></div><div class="skeleton-line w70"></div><div class="skeleton-line w50"></div></div>';

    const c = document.getElementById('chat-messages');
    const msgEl = document.createElement('div');
    msgEl.className = 'chat-msg agent';
    msgEl.innerHTML = '<div class="sender">玄机子</div><div class="bubble"><div class="ai-loading"><span></span><span></span><span></span></div></div>';
    c.appendChild(msgEl);
    const bubble = msgEl.querySelector('.bubble');

    let replyText = '';
    let currentTool = null;
    let reportBuf = '';
    let currentTab = forceTab || 'overview';
    const reportStatus = document.getElementById('report-status');

    apiChatStream(chartId, prompt,
        function(delta, tool) {
            if (tool) currentTool = tool;
            replyText += delta;
            // Incremental update via textContent (avoids full DOM rebuild per token)
            if (!bubble._streamReady) {
                bubble.innerHTML = '<span class="stream-text"></span><span class="streaming-cursor">▌</span>';
                bubble._streamReady = true;
            }
            bubble.querySelector('.stream-text').textContent = replyText;
            if (c.scrollHeight - c.scrollTop - c.clientHeight < 50) {
                c.scrollTop = c.scrollHeight;
            }
        },
        function(text, tab) {
            if (forceTab) {
                tab = forceTab;
            } else if (currentTab === 'overview' && tab !== 'overview') {
                var store = ReportTabs._getStore();
                var baseTab = tab;
                var counter = 1;
                while (store[tab] !== undefined) {
                    counter++;
                    tab = baseTab + '_' + counter;
                }
                currentTab = tab;
            }
            reportBuf = text;
            showReportStreaming(tab, reportBuf);
        },
        function(toolName) {
            currentTool = toolName;
            const sender = msgEl.querySelector('.sender');
            sender.innerHTML = '玄机子 <span class="tool-tag">🔧 ' + toolName + '</span>';
            reportStatus.innerHTML = '⏳ 玄机子正在' + toolName + '…';
        },
        function(corrections) {
            // Finalize: remove cursor, set content with line breaks
            bubble.innerHTML = (replyText || '分析完成，请查看右侧报告。').replace(/\n/g, '<br>');
            bubble._streamReady = false;
            reportStatus.innerHTML = '✅ 分析完成';
            if (reportBuf) showReportFinal(currentTab, reportBuf);
            if (currentTool) {
                const sender = msgEl.querySelector('.sender');
                sender.innerHTML = '玄机子 <span class="tool-tag">🔧 ' + currentTool + '</span>';
            }
            var correctBtn = document.getElementById('correct-btn');
            if (correctBtn) correctBtn.style.display = 'inline-block';
            if (onSuccess) onSuccess();
        }
    );
}

function ensureReportTab(tabId) { ReportTabs.set(tabId, ''); }
function activateReportTab(tabId) { ReportTabs.switchTo(tabId); }

function showReportStreaming(tab, content) {
    var store = ReportTabs._getStore();
    store[tab] = content;
    ReportTabs._active = tab;
    ReportTabs._renderTabs();
    document.getElementById('report-content').innerHTML =
        renderMarkdown(content) + '<span class="streaming-cursor">▌</span>';
    document.getElementById('report-status').classList.remove('done');
}

function _buildOverview() {
    var store = ReportTabs._getStore();
    var getLabel = ReportTabs._tabLabel || function(t) { return t; };
    var parts = [];
    for (var tid in store) {
        if (tid === 'overview') continue;
        if (store[tid]) {
            var h2s = store[tid].match(/^## (.+)$/gm);
            if (h2s && h2s.length > 0) {
                parts.push('#### ' + getLabel(tid));
                for (var i = 0; i < Math.min(h2s.length, 5); i++) {
                    parts.push('- ' + h2s[i].replace(/^## /, ''));
                }
            } else {
                parts.push('- **' + getLabel(tid) + '**：已有分析结果');
            }
        }
    }
    if (parts.length === 0) return '输入出生信息后，报告将在此显示';
    return '# 分析总览\n\n' + parts.join('\n');
}

export function showReportFinal(tab, content) {
    var store = ReportTabs._getStore();
    store[tab] = content;
    store['overview'] = _buildOverview();
    ReportTabs._active = tab;
    ReportTabs._renderTabs();
    document.getElementById('report-content').innerHTML = renderMarkdown(content);
    document.getElementById('report-status').classList.add('done');
    document.getElementById('report-pdf-btn').classList.remove('hidden');
    var cur = MingzhuManager.getCurrent();
    if (cur) { PersistenceSync.saveReport(cur.chart_id, tab, content); }
}

function _hideToolBars() {
    ['zeri-bar','liunian-bar','name-bar','hehun-bar'].forEach(function(id) {
        document.getElementById(id).classList.add('hidden');
    });
}

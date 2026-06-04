// ================================================================
// 玄机子 Frontend — Markdown 渲染
// ================================================================

function _escHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function _renderMdTable(lines) {
    const parseRow = function(line) {
        return line.replace(/^\||\|$/g, '').split('|').map(function(c) { return _escHtml(c.trim()); });
    };
    const header = parseRow(lines[0]);
    let h = '<table><thead><tr>';
    header.forEach(function(c) { h += '<th>' + c + '</th>'; });
    h += '</tr></thead><tbody>';
    for (let i = 2; i < lines.length; i++) {
        const cells = parseRow(lines[i]);
        h += '<tr>';
        cells.forEach(function(c) { h += '<td>' + c + '</td>'; });
        h += '</tr>';
    }
    h += '</tbody></table>';
    return h;
}

function _renderMdBlock(block) {
    return block
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/\n/g, '<br>');
}

function renderMarkdown(md) {
    if (!md) return '';
    const blocks = md.split(/\n\n/);
    return blocks.map(function(block) {
        const lines = block.split('\n');
        if (lines.length >= 2 && lines[0].startsWith('|') && /^\|[\s\-:|]*\-+[\s\-:|]*\|$/.test(lines[1])) {
            return _renderMdTable(lines);
        }
        const nonEmpty = lines.filter(function(l) { return l.trim() !== ''; });
        if (nonEmpty.length > 0 && nonEmpty.every(function(l) { return /^- /.test(l); })) {
            return '<ul>' + nonEmpty.map(function(l) { return _renderMdBlock(l); }).join('') + '</ul>';
        }
        return _renderMdBlock(block);
    }).join('<br><br>');
}

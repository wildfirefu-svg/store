#!/usr/bin/env python3
"""
Convert a BaZi analysis markdown report to a professionally styled PDF.
Supports 4 templates: dark (default), modern, scroll, night.
Usage: python report_to_pdf.py input.md -o output.pdf [--template dark|modern|scroll|night]
"""

import argparse, re, os, sys
from fpdf import FPDF

FONT_CANDIDATES_HEADER = [
    'C:/Windows/Fonts/simhei.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc',
]
FONT_CANDIDATES_BODY = [
    'C:/Windows/Fonts/simsun.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc',
]

def _first_existing(paths):
    return next((p for p in paths if os.path.exists(p)), paths[0])

FONT_HEADER = _first_existing(FONT_CANDIDATES_HEADER)
FONT_BODY = _first_existing(FONT_CANDIDATES_BODY)
A4_W, A4_H = 210, 297

TEMPLATES = {
    'dark': {  # Classic Dark (default)
        'name': 'Classic Dark', 'cover_bg': (28,32,48), 'cover_text': (255,255,255),
        'accent': (120,100,70), 'h1': (65,80,110), 'h2': (50,60,80),
        'body': (50,50,60), 'muted': (145,145,155), 'line': (215,218,225),
        'tbl_hd': (45,55,72), 'tbl_hd_txt': (255,255,255),
        'tbl_row0': (249,250,253), 'tbl_row1': (255,255,255),
        'code_bg': (248,249,252), 'code_txt': (75,80,92),
        'disc_bg': (255,252,238), 'disc_bd': (215,195,105), 'disc_txt': (140,120,50),
        'ji': (55,140,75), 'xiong': (185,55,55), 'ping': (140,130,90),
        'header_line': (215,218,225),
    },
    'modern': {  # Clean Modern
        'name': 'Clean Modern', 'cover_bg': (255,255,255), 'cover_text': (13,115,119),
        'accent': (13,115,119), 'h1': (13,115,119), 'h2': (45,52,54),
        'body': (45,52,54), 'muted': (150,155,160), 'line': (220,225,230),
        'tbl_hd': (13,115,119), 'tbl_hd_txt': (255,255,255),
        'tbl_row0': (245,250,251), 'tbl_row1': (255,255,255),
        'code_bg': (245,250,251), 'code_txt': (45,52,54),
        'disc_bg': (240,250,250), 'disc_bd': (13,115,119), 'disc_txt': (13,115,119),
        'ji': (13,115,119), 'xiong': (200,60,60), 'ping': (150,140,80),
        'header_line': (220,225,230),
    },
    'scroll': {  # Traditional Scroll
        'name': 'Traditional Scroll', 'cover_bg': (245,240,232), 'cover_text': (196,30,58),
        'accent': (196,30,58), 'h1': (74,55,40), 'h2': (100,75,55),
        'body': (74,55,40), 'muted': (160,145,130), 'line': (200,190,175),
        'tbl_hd': (74,55,40), 'tbl_hd_txt': (255,250,240),
        'tbl_row0': (250,247,240), 'tbl_row1': (255,252,248),
        'code_bg': (250,247,240), 'code_txt': (74,55,40),
        'disc_bg': (255,248,240), 'disc_bd': (196,30,58), 'disc_txt': (140,60,40),
        'ji': (90,130,70), 'xiong': (196,30,58), 'ping': (160,130,70),
        'header_line': (200,190,175),
    },
    'night': {  # Dark Mode
        'name': 'Night Mode', 'cover_bg': (13,17,23), 'cover_text': (88,166,255),
        'accent': (88,166,255), 'h1': (88,166,255), 'h2': (200,210,220),
        'body': (201,209,217), 'muted': (110,118,129), 'line': (48,54,61),
        'tbl_hd': (22,27,34), 'tbl_hd_txt': (88,166,255),
        'tbl_row0': (22,27,34), 'tbl_row1': (13,17,23),
        'code_bg': (22,27,34), 'code_txt': (201,209,217),
        'disc_bg': (22,27,34), 'disc_bd': (88,166,255), 'disc_txt': (139,148,158),
        'ji': (63,185,80), 'xiong': (248,81,73), 'ping': (210,168,0),
        'header_line': (48,54,61),
    },
}


class BaziReportPDF(FPDF):
    def __init__(self, template='dark'):
        super().__init__('P', 'mm', 'A4')
        self.set_auto_page_break(True, 20)
        self.set_left_margin(20)
        self.set_right_margin(20)
        self._tpl = TEMPLATES.get(template, TEMPLATES['dark'])
        self._tpl_name = template

        self._font_h = os.path.exists(FONT_HEADER)
        self._font_b = os.path.exists(FONT_BODY)
        if self._font_h: self.add_font('CJKH', '', FONT_HEADER)
        if self._font_b: self.add_font('CJKB', '', FONT_BODY)
        self._h_font = 'CJKH' if self._font_h else ('CJKB' if self._font_b else 'Helvetica')
        self._b_font = 'CJKB' if self._font_b else ('CJKH' if self._font_h else 'Helvetica')

    def _c(self, key):
        return self._tpl.get(key, (0,0,0))

    def header(self):
        if self.page_no() <= 1: return
        self.set_draw_color(*self._c('header_line'))
        self.set_line_width(0.1)
        self.line(self.l_margin, self.get_y()+2, self.w-self.r_margin, self.get_y()+2)
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font(self._b_font, '', 6.5)
        self.set_text_color(*self._c('muted'))
        self.cell(0, 8, str(self.page_no()), align='C')

    def draw_cover(self, title, meta_lines):
        mid_x = self.w / 2
        bg = self._c('cover_bg')
        txt_c = self._c('cover_text')
        accent = self._c('accent')

        self.set_fill_color(*bg)
        self.rect(0, 0, A4_W, A4_H, 'F')

        self.set_draw_color(*accent)
        self.set_line_width(0.6)
        self.line(0, 42, A4_W, 42)
        self.set_line_width(0.2)
        self.line(0, 44, A4_W, 44)

        self.set_y(62)
        self.set_font(self._h_font, '', 24)
        self.set_text_color(*txt_c)
        self.multi_cell(0, 13, title, align='C')

        self.ln(6)
        self.set_draw_color(*accent)
        self.set_line_width(0.5)
        self.line(mid_x-35, self.get_y(), mid_x+35, self.get_y())
        self.ln(10)

        if meta_lines:
            self.set_font(self._b_font, '', 9.5)
            self.set_text_color(*self._c('muted'))
            for ml in meta_lines[:4]:
                clean = strip_formatting(ml)
                if clean.strip():
                    self.cell(0, 6.5, clean, align='C')
                    self.ln(6.5)

        self.set_y(A4_H - 50)
        self.set_draw_color(*accent)
        self.set_line_width(0.3)
        self.line(mid_x-25, A4_H-50, mid_x+25, A4_H-50)
        self.set_y(A4_H - 42)
        self.set_font(self._b_font, '', 8)
        self.set_text_color(*self._c('muted'))
        self.cell(0, 6, '玄机子 · 八字命理分析', align='C')
        self.set_y(30)

    def draw_section(self, text, level):
        text = strip_formatting(text)
        usable_w = self.w - self.l_margin - self.r_margin
        if level == 1:
            self.ln(7)
            self.set_fill_color(*self._c('h1'))
            self.rect(self.l_margin, self.get_y(), 3.5, 10, 'F')
            self.set_font(self._h_font, '', 14)
            self.set_text_color(*self._c('h1'))
            self.set_x(self.l_margin + 6)
            self.cell(0, 10, text, align='L')
            self.set_text_color(*self._c('body'))
            self.ln(4)
            self.set_draw_color(*self._c('line'))
            self.set_line_width(0.18)
            self.line(self.l_margin, self.get_y(), self.w-self.r_margin, self.get_y())
            self.ln(6)
        elif level == 2:
            self.ln(4)
            self.set_font(self._h_font, '', 12)
            self.set_text_color(*self._c('h2'))
            self.cell(0, 8, text, align='L')
            self.set_text_color(*self._c('body'))
            self.ln(10)
        elif level == 3:
            self.ln(2)
            self.set_font(self._h_font, '', 10.5)
            self.set_text_color(*self._c('h2'))
            self.cell(0, 7, '  '+text, align='L')
            self.set_text_color(*self._c('body'))
            self.ln(8)

    def draw_paragraph(self, text):
        text = strip_formatting(text)
        if not text.strip(): self.ln(2); return
        self.set_font(self._b_font, '', 9)
        self.set_text_color(*self._c('body'))
        self.multi_cell(self.w-self.l_margin-self.r_margin, 5.2, text, align='L')
        self.ln(1.5)

    def draw_bullet(self, text):
        self.set_font(self._h_font, '', 9)
        self.set_text_color(*self._c('h1'))
        self.cell(5, 5.2, '·')
        self.set_text_color(*self._c('body'))
        self.set_font(self._b_font, '', 9)
        self.multi_cell(self.w-self.l_margin-self.r_margin-5, 5.2, strip_formatting(text), align='L')
        self.ln(0.5)

    def draw_hr(self):
        self.ln(3)
        self.set_draw_color(*self._c('line'))
        self.set_line_width(0.15)
        cx = self.w/2
        self.line(cx-28, self.get_y(), cx+28, self.get_y())
        self.ln(4)

    def draw_disclaimer(self, text):
        self.ln(8)
        usable_w = self.w-self.l_margin-self.r_margin
        self.set_draw_color(*self._c('disc_bd'))
        self.set_fill_color(*self._c('disc_bg'))
        self.set_font(self._b_font, '', 7.5)
        self.set_text_color(*self._c('disc_txt'))
        self.set_x(self.l_margin+3)
        self.multi_cell(usable_w-6, 4.5, strip_formatting(text), align='L', fill=True)
        self.set_text_color(*self._c('body'))

    def draw_bazi_chart(self, code_text):
        lines = [l for l in code_text.split('\n') if l.strip()]
        if len(lines) < 2: self.draw_code_block(code_text); return
        usable_w = self.w-self.l_margin-self.r_margin
        self.ln(3)
        label_w = 18
        data_w = (usable_w-label_w)/4
        self.set_draw_color(*self._c('line'))
        self.set_line_width(0.1)
        for lidx, line in enumerate(lines):
            parts = re.split(r'\s{2,}', line.strip())
            if len(parts) < 2: continue
            label = parts[0]; values = (parts[1:5] if len(parts)>1 else []) + ['']*4
            values = values[:4]
            is_hdr, row_h = (lidx == 0), (7 if lidx==0 else 6.5)
            if self.get_y()+row_h > self.h-self.b_margin: self.add_page()
            y0, x0 = self.get_y(), self.l_margin
            if is_hdr:
                self.set_fill_color(*self._c('tbl_hd'))
                self.set_text_color(*self._c('tbl_hd_txt'))
                self.set_font(self._h_font, '', 8)
            else:
                bg = self._c('tbl_row0') if lidx%2==0 else self._c('tbl_row1')
                self.set_fill_color(*bg)
                self.set_text_color(*self._c('body'))
                self.set_font(self._b_font, '', 7.5)
            self.rect(x0, y0, label_w, row_h, 'F')
            self.set_xy(x0+1.5, y0+0.8)
            self.cell(label_w-3, row_h-1.6, label, align='C')
            for ci, val in enumerate(values):
                cx = x0+label_w+ci*data_w
                if is_hdr:
                    self.set_fill_color(*self._c('tbl_hd'))
                    self.set_text_color(*self._c('tbl_hd_txt'))
                else:
                    bg = self._c('tbl_row0') if lidx%2==0 else self._c('tbl_row1')
                    self.set_fill_color(*bg)
                    self.set_text_color(*self._c('body'))
                self.rect(cx, y0, data_w, row_h, 'F')
                self.set_xy(cx+1, y0+0.8)
                self.cell(data_w-2, row_h-1.6, val, align='C')
            self.set_y(y0+row_h)
        self.set_text_color(*self._c('body'))
        self.set_font(self._b_font, '', 9)
        self.ln(3)

    def draw_table(self, rows):
        if len(rows) < 2: return
        self.ln(3)
        ncols = len(rows[0])
        usable_w = self.w-self.l_margin-self.r_margin
        col_w = self._calc_col_widths(ncols, rows, usable_w)
        fsize, line_h, px, py = 7.5, 4.8, 2.0, 1.2
        x0 = self.l_margin
        self.set_font(self._b_font, '', fsize)
        for ridx, row in enumerate(rows):
            max_lines, cell_info = 1, []
            for cidx in range(min(len(row), ncols)):
                clean = strip_formatting(row[cidx])
                cw = col_w[cidx] if cidx < len(col_w) else col_w[-1]
                tw = max(cw-2*px, 5)
                measured = self.multi_cell(tw, line_h, clean, dry_run=True, output="LINES")
                nl = max(1, len(measured))
                cell_info.append((clean, nl))
                max_lines = max(max_lines, nl)
            row_h = max_lines*line_h + 2*py
            if self.get_y()+row_h > self.h-self.b_margin: self.add_page()
            y0 = self.get_y()
            for cidx, (clean, nl) in enumerate(cell_info):
                cw = col_w[cidx] if cidx < len(col_w) else col_w[-1]
                cx = x0+sum(col_w[:cidx])
                if ridx == 0:
                    self.set_fill_color(*self._c('tbl_hd'))
                    self.set_text_color(*self._c('tbl_hd_txt'))
                    self.set_font(self._h_font, '', fsize)
                else:
                    bg = self._c('tbl_row0') if ridx%2==0 else self._c('tbl_row1')
                    self.set_fill_color(*bg)
                    self.set_text_color(*self._c('body'))
                    self.set_font(self._b_font, '', fsize)
                self.rect(cx, y0, cw, row_h, 'F')
                self.set_xy(cx+px, y0+py)
                self.multi_cell(cw-2*px, line_h, clean, align='L')
            self.set_y(y0+row_h)
        self.set_text_color(*self._c('body'))
        self.ln(4)

    def _calc_col_widths(self, ncols, rows, usable_w):
        col_max = [3.0]*ncols
        for row in rows:
            for i in range(min(len(row), ncols)):
                text = strip_formatting(row[i])
                w = sum(2.0 if ord(c)>127 else 1.0 for c in text)
                col_max[i] = max(col_max[i], w)
        col_w = [min(w*2.2+6, 60) for w in col_max]
        total = sum(col_w)
        if total > usable_w: col_w = [w*usable_w/total for w in col_w]
        return col_w

    def draw_code_block(self, content):
        self.ln(3)
        usable_w = self.w-self.l_margin-self.r_margin
        self.set_fill_color(*self._c('code_bg'))
        self.set_text_color(*self._c('code_txt'))
        self.set_font(self._b_font, '', 7)
        line_h = 4.2
        lines = content.split('\n')
        block_h = len(lines)*line_h+4
        if self.get_y()+block_h > self.h-self.b_margin: self.add_page()
        y0 = self.get_y()
        self.rect(self.l_margin, y0, usable_w, block_h, 'F')
        self.set_xy(self.l_margin+2, y0+2)
        for cline in lines:
            self.cell(usable_w-4, line_h, cline, align='L')
            self.ln(line_h)
        self.set_y(y0+block_h+2)
        self.set_text_color(*self._c('body'))


def strip_formatting(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    for ch in ['⚠️','⚠','🟢','📅','•','️','→','←','↑','↓','⭐','⛔','✅','❌','⭐']:
        text = text.replace(ch, '')
    return text


def parse_markdown_to_blocks(lines):
    blocks, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip(): blocks.append(('blank', None)); i += 1; continue
        if line.strip().startswith('```'):
            code_lines = []; i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i]); i += 1
            i += 1; blocks.append(('code', '\n'.join(code_lines))); continue
        if '|' in line and i+1 < len(lines) and '|---' in lines[i+1]:
            table_rows = [[c.strip() for c in line.split('|')[1:-1]]]; i += 2
            while i < len(lines) and '|' in lines[i]:
                table_rows.append([c.strip() for c in lines[i].split('|')[1:-1]]); i += 1
            table_rows = [r for r in table_rows if not all(re.match(r'^[-:]+$',c) for c in r)]
            blocks.append(('table', table_rows)); continue
        for level, prefix in [(1,'# '),(2,'## '),(3,'### ')]:
            if line.startswith(prefix):
                blocks.append((f'h{level}', line[len(prefix):].strip())); break
        else:
            if re.match(r'^[-*]{3,}\s*$', line.strip()): blocks.append(('hr', None))
            elif line.strip().startswith(('- ','* ')): blocks.append(('bullet', line.strip()[2:]))
            else: blocks.append(('para', line))
        i += 1
    return blocks


def generate_pdf(md_path, pdf_path, template='dark'):
    with open(md_path, 'r', encoding='utf-8') as f: lines = f.readlines()
    blocks = parse_markdown_to_blocks(lines)
    pdf = BaziReportPDF(template)

    first_h1 = None; meta_lines = []
    for btype, content in blocks:
        if btype == 'h1' and first_h1 is None: first_h1 = content
        elif btype == 'para' and content.strip() and first_h1:
            meta_lines.append(content.strip())
            if len(meta_lines) >= 3: break

    pdf.add_page()
    if first_h1: pdf.draw_cover(first_h1, meta_lines); pdf.add_page()

    first_h1_done = False
    for btype, content in blocks:
        if btype == 'blank': continue
        elif btype == 'h1':
            if not first_h1_done: first_h1_done = True; continue
            pdf.draw_section(content, level=1)
        elif btype == 'h2': pdf.draw_section(content, level=2)
        elif btype == 'h3': pdf.draw_section(content, level=3)
        elif btype == 'para':
            pdf.draw_disclaimer(content) if '免责声明' in content else pdf.draw_paragraph(content)
        elif btype == 'code':
            pdf.draw_bazi_chart(content) if '年柱' in content and '月柱' in content else pdf.draw_code_block(content)
        elif btype == 'table': pdf.draw_table(content)
        elif btype == 'hr': pdf.draw_hr()
        elif btype == 'bullet': pdf.draw_bullet(content)

    pdf.output(pdf_path)
    print(f'PDF generated [{template}]: {pdf_path}')


def main():
    parser = argparse.ArgumentParser(description='BaZi Report PDF Generator')
    parser.add_argument('input', help='Input markdown file')
    parser.add_argument('-o', '--output', default=None)
    parser.add_argument('-t', '--template', choices=['dark','modern','scroll','night'], default='dark',
                       help='Template style (default: dark)')
    args = parser.parse_args()
    if args.output is None: args.output = os.path.splitext(args.input)[0] + '.pdf'
    generate_pdf(args.input, args.output, args.template)

if __name__ == '__main__':
    main()

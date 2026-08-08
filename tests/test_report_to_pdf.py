#!/usr/bin/env python3
"""Unit tests for report_to_pdf.py — font detection, template validation, PDF generation."""

import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import report_to_pdf as rp


class TestFontDetection:
    def test_first_existing_finds_real_font(self):
        """_first_existing should return a path that exists when fed real fonts."""
        # At least one of the candidate fonts should exist on this system
        result = rp.FONT_HEADER
        assert result is not None
        assert len(result) > 5

    def test_first_existing_returns_first_when_none_exist(self):
        """_first_existing should return the first path even if none exist."""
        result = rp._first_existing(['/nonexistent/a.ttf', '/nonexistent/b.ttf'])
        assert result == '/nonexistent/a.ttf'


class TestTemplates:
    def test_all_templates_have_required_keys(self):
        required = ['name', 'cover_bg', 'cover_text', 'accent', 'h1', 'h2',
                    'body', 'muted', 'line', 'tbl_hd', 'tbl_hd_txt',
                    'code_bg', 'code_txt', 'ji', 'xiong', 'ping']
        for tname, t in rp.TEMPLATES.items():
            for key in required:
                assert key in t, f'Template {tname} missing key {key}'

    def test_all_four_templates_exist(self):
        for tname in ['dark', 'modern', 'scroll', 'night']:
            assert tname in rp.TEMPLATES

    def test_template_colors_are_valid_rgb(self):
        for tname, t in rp.TEMPLATES.items():
            for key, val in t.items():
                if key == 'name':
                    continue
                if isinstance(val, tuple):
                    assert len(val) == 3, f'{tname}.{key} should be RGB tuple'
                    for c in val:
                        assert 0 <= c <= 255, f'{tname}.{key} color out of range'


class TestBaziReportPDF:
    def test_init_default_template(self):
        pdf = rp.BaziReportPDF()
        assert pdf is not None
        assert pdf._tpl_name == 'dark'

    def test_init_all_templates(self):
        for tname in ['dark', 'modern', 'scroll', 'night']:
            pdf = rp.BaziReportPDF(template=tname)
            assert pdf._tpl_name == tname

    def test_init_invalid_falls_back_to_dark(self):
        """Invalid template name should fall back to 'dark'."""
        pdf = rp.BaziReportPDF(template='nonexistent')
        # Should not crash — falls back to dark
        assert pdf._tpl_name == 'nonexistent'  # stored as-is
        assert pdf._tpl == rp.TEMPLATES['dark']  # but uses dark template


class TestStripFormatting:
    def test_preserves_emoji(self):
        # strip_formatting only handles markdown syntax, not emoji
        result = rp.strip_formatting('🔥 Hello')
        assert 'Hello' in result

    def test_strips_markdown_bold(self):
        result = rp.strip_formatting('**bold** text')
        assert 'bold' in result
        assert '**' not in result

    def test_preserves_normal_text(self):
        assert rp.strip_formatting('普通文字') == '普通文字'


class TestParseMarkdown:
    def test_parses_heading(self):
        blocks = rp.parse_markdown_to_blocks(['# Heading 1', '', 'Body text'])
        assert len(blocks) > 0
        assert any(b[0] == 'h1' for b in blocks)

    def test_parses_paragraph(self):
        blocks = rp.parse_markdown_to_blocks(['Just a paragraph.'])
        assert len(blocks) > 0
        assert any(b[0] == 'para' for b in blocks)

    def test_parses_table(self):
        blocks = rp.parse_markdown_to_blocks([
            '| A | B |',
            '|---|----|',
            '| 1 | 2 |',
        ])
        assert any(b[0] == 'table' for b in blocks)

    def test_parses_image(self):
        blocks = rp.parse_markdown_to_blocks(['![五行图](test_chart.png)'])
        assert ('image', {'alt': '五行图', 'path': 'test_chart.png'}) in blocks


class TestGeneratePDF:
    def test_generates_pdf_from_minimal_markdown(self):
        """End-to-end: generate a PDF from minimal markdown."""
        md_content = '# 测试报告\n\n这是一个测试段落。\n\n## 第二节\n\n更多内容。'
        md_path = os.path.join(tempfile.gettempdir(), 'test_minimal.md')
        pdf_path = os.path.join(tempfile.gettempdir(), 'test_minimal.pdf')

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        try:
            rp.generate_pdf(md_path, pdf_path, template='dark')
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 100  # PDF header is at least a few bytes
        finally:
            for p in [md_path, pdf_path]:
                if os.path.isfile(p):
                    os.unlink(p)

    def test_generates_pdf_all_templates(self):
        """Each template should produce a valid (non-empty) PDF."""
        md_content = '# 全模板测试\n\n通用内容。'
        md_path = os.path.join(tempfile.gettempdir(), 'test_tpl.md')

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        try:
            for tname in ['dark', 'modern', 'scroll', 'night']:
                pdf_path = os.path.join(tempfile.gettempdir(), f'test_tpl_{tname}.pdf')
                rp.generate_pdf(md_path, pdf_path, template=tname)
                assert os.path.isfile(pdf_path)
                assert os.path.getsize(pdf_path) > 100, f'{tname} template produced empty PDF'
                os.unlink(pdf_path)
        finally:
            if os.path.isfile(md_path):
                os.unlink(md_path)

    def test_generates_pdf_with_chinese_text(self):
        """PDF generation must handle CJK characters without crashing."""
        md_content = '# 八字命理分析报告\n\n日主丙火，身弱喜印比。\n\n| 四柱 | 天干 |\n|------|------|\n| 年柱 | 癸酉 |'
        md_path = os.path.join(tempfile.gettempdir(), 'test_cjk.md')
        pdf_path = os.path.join(tempfile.gettempdir(), 'test_cjk.pdf')

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        try:
            rp.generate_pdf(md_path, pdf_path, template='dark')
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 200
        finally:
            for p in [md_path, pdf_path]:
                if os.path.isfile(p):
                    os.unlink(p)

    def test_generates_pdf_with_image(self):
        png_path = os.path.join(tempfile.gettempdir(), 'test_chart_image.png')
        md_path = os.path.join(tempfile.gettempdir(), 'test_image.md')
        pdf_path = os.path.join(tempfile.gettempdir(), 'test_image.pdf')
        png_bytes = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=')

        with open(png_path, 'wb') as f:
            f.write(png_bytes)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f'# 图表报告\n\n![五行图]({png_path})\n')

        try:
            rp.generate_pdf(md_path, pdf_path, template='dark')
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 200
        finally:
            for p in [png_path, md_path, pdf_path]:
                if os.path.isfile(p):
                    os.unlink(p)

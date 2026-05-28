---
name: pdf-templates
description: Multiple beautiful PDF templates for BaZi analysis reports. Use when generating reports to select and apply a visual style.
---

# PDF Report Templates

Choose from 4 template styles when generating BaZi analysis reports. Each template defines
cover design, typography, color palette, table styling, and layout conventions.

## Template 1: Classic Dark (经典暗金) — DEFAULT

A professional dark-header design with gold accents. Best for formal reports.

**Colors**: Dark navy (#1a1a2e) header, gold (#c9a96e) accents, white body, light gray tables.
**Cover**: Full-page dark background with gold double-line separator, centered title in white.
**Sections**: Left gold bar markers for H1, dark blue-gray H2, indented H3.
**Tables**: Dark header row (navy), alternating row colors (light gray/white).

```
报告生成时使用: report_to_pdf.py 默认模板
```

## Template 2: Clean Modern (清新现代)

Minimalist design with teal accents. Best for简洁报告.

**Colors**: White background, teal (#0d7377) accents, charcoal text (#2d3436), soft gray tables.
**Cover**: White cover with teal top band, large title, small subtitle below.
**Sections**: Teal H1 with thin underline, charcoal H2, indented gray H3.
**Tables**: Teal header row, white rows with thin bottom borders.

## Template 3: Traditional Scroll (古风卷轴)

Traditional Chinese aesthetic with warm earth tones. Best for深度命理分析.

**Colors**: Cream/parchment (#f5f0e8) background, dark brown (#4a3728) text, vermillion (#c41e3a) accents.
**Cover**: Parchment background with vermillion seal-like square, vertical title.
**Sections**: Dark brown H1 with Chinese-style side markers, vermillion H2.
**Tables**: Brown header, parchment rows with thin brown borders.

## Template 4: Night Mode (暗夜模式)

Dark background with bright accents. Best for screen reading.

**Colors**: Dark (#0d1117) background, cyan (#58a6ff) accents, light gray (#c9d1d9) text.
**Cover**: Full dark with cyan glow title, subtle grid pattern.
**Sections**: Cyan H1 with glow effect, light gray H2, indented H3.
**Tables**: Dark blue header, dark gray rows, thin cyan borders.

## Usage

When generating a report, the agent should:
1. Ask or decide which template to use based on user preference
2. Pass the template choice to `report_to_pdf.py --template <name>`
3. For custom color overrides: `report_to_pdf.py --template modern --color-accent "#ff6b6b"`

## Implementation Note

The `report_to_pdf.py` script currently uses the Classic Dark template by default.
For other templates, the script's color palette and layout constants should be parameterized.
See the COLOR PALETTE section in report_to_pdf.py for customization points.

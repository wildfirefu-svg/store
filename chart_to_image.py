#!/usr/bin/env python3
"""Generate static chart images from BaZi visualization data using matplotlib.

Produces 4 PNG files (wuxing radar, shishen pie, dayun line, liunian bar)
suitable for embedding into PDF reports.
"""

import os
import tempfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_CJK_FONT = None
for _p in [
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]:
    if os.path.exists(_p):
        _CJK_FONT = _p
        break

if _CJK_FONT:
    from matplotlib.font_manager import FontProperties
    _CJK_FP = FontProperties(fname=_CJK_FONT)
    plt.rcParams["font.family"] = _CJK_FP.get_name()
    plt.rcParams["axes.unicode_minus"] = False


def _wuxing_radar(data, path):
    names = ["金", "木", "水", "火", "土"]
    values = [float(data.get(n, 0)) for n in names]
    N = len(names)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    values_plot = values + values[:1]
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=(3.6, 3.6), subplot_kw={"polar": True})
    ax.fill(angles, values_plot, color="#4a7c59", alpha=0.25)
    ax.plot(angles, values_plot, color="#4a7c59", linewidth=2)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(names, fontsize=11)
    ax.set_title("五行分布", fontsize=13, pad=16)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _shishen_pie(data, path):
    if not data:
        data = {"无": 1}
    labels = list(data.keys())
    sizes = [float(v) for v in data.values()]
    cmap = plt.cm.Set3
    colors = [cmap(i / max(len(labels), 1)) for i in range(len(labels))]
    fig, ax = plt.subplots(figsize=(3.6, 3.6))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct="%1.0f%%",
        colors=colors, startangle=90, textprops={"fontsize": 9},
    )
    ax.set_title("十神分布", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _dayun_line(data, path):
    if not data:
        data = [{"age": 0, "gan_zhi": "", "score": 0}]
    ages = [f"{d.get('age', '')}岁" for d in data]
    scores = [float(d.get("score", 0)) for d in data]
    fig, ax = plt.subplots(figsize=(5.5, 2.8))
    ax.plot(ages, scores, marker="o", color="#3a6ea5", linewidth=2)
    ax.fill_between(ages, scores, alpha=0.15, color="#3a6ea5")
    ax.set_title("大运趋势", fontsize=13)
    ax.set_ylabel("运势评分")
    plt.xticks(rotation=30, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _liunian_bar(data, path):
    if not data:
        data = [{"year": 0, "gan_zhi": "", "score": 0}]
    years = [str(d.get("year", "")) for d in data]
    scores = [float(d.get("score", 0)) for d in data]
    fig, ax = plt.subplots(figsize=(5.5, 2.8))
    colors = ["#c0392b" if s < 0 else "#27ae60" for s in scores]
    ax.bar(years, scores, color=colors, alpha=0.8)
    ax.set_title("流年运势", fontsize=13)
    ax.set_ylabel("运势评分")
    plt.xticks(rotation=30, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_chart_images(viz_data, output_dir=None):
    """Generate 4 chart PNGs from visualization data.

    Args:
        viz_data: dict with keys 'wuxing', 'shishen', 'dayun', 'liunian'.
        output_dir: directory for PNGs. Defaults to a temp dir.

    Returns:
        dict mapping chart name -> absolute file path of the PNG.
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="bazi_chart_")
    os.makedirs(output_dir, exist_ok=True)

    paths = {}
    chart_funcs = [
        ("wuxing", _wuxing_radar, viz_data.get("wuxing", {})),
        ("shishen", _shishen_pie, viz_data.get("shishen", {})),
        ("dayun", _dayun_line, viz_data.get("dayun", [])),
        ("liunian", _liunian_bar, viz_data.get("liunian", [])),
    ]
    for name, func, data in chart_funcs:
        p = os.path.join(output_dir, f"{name}.png")
        try:
            func(data, p)
            paths[name] = p
        except Exception:
            pass
    return paths

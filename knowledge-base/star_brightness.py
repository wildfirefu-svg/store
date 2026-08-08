"""
紫微斗数星曜庙旺得平陷查表模块 (v2)

六等级制: 庙(5) > 旺(4) > 得(3) > 利(2) > 平(1) > 陷(0)

用法:
    from star_brightness import get_brightness, get_brightness_value, get_all_stars_in_palace
    
    level = get_brightness("紫微", "午")       # "庙"
    val   = get_brightness_value("太阳", "子") # 0 (陷)
    stars = get_all_stars_in_palace("寅")       # {"紫微": "旺", "天机": "旺", ...}
"""

import json
from pathlib import Path

BRIGHTNESS_MAP = {
    "庙": 5, "旺": 4, "得": 3, "利": 2, "平": 1, "陷": 0
}

VALUE_TO_BRIGHTNESS = {v: k for k, v in BRIGHTNESS_MAP.items()}

DIZHI = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]

_DATA = None

def _get_data():
    global _DATA
    if _DATA is None:
        json_path = Path(__file__).parent / "star_brightness.json"
        with open(json_path, "r", encoding="utf-8") as f:
            _DATA = json.load(f)
    return _DATA


def get_brightness(star_name: str, dizhi: str) -> str:
    """查询星曜在特定地支的亮度等级"""
    data = _get_data()
    star = data["stars"].get(star_name)
    if not star:
        raise ValueError(f"未知星曜: {star_name}")
    if dizhi not in DIZHI:
        raise ValueError(f"未知地支: {dizhi}")
    return star["brightness"][DIZHI.index(dizhi)]


def get_brightness_value(star_name: str, dizhi: str) -> int:
    """查询星曜亮度数值 (0-5): 5=庙 4=旺 3=得 2=利 1=平 0=陷"""
    return BRIGHTNESS_MAP[get_brightness(star_name, dizhi)]


def get_all_stars_in_palace(dizhi: str) -> dict[str, str]:
    """查询某地支宫位中所有十四主星的亮度"""
    data = _get_data()
    return {name: star["brightness"][DIZHI.index(dizhi)] for name, star in data["stars"].items()}


def get_palace_score(dizhi: str) -> int:
    """计算某宫位亮度总分 (满分70)"""
    return sum(get_brightness_value(name, dizhi) for name in _get_data()["stars"])


def get_brightness_all_dizhi(star_name: str) -> dict[str, str]:
    """查询星曜在所有十二地支的亮度"""
    return {dz: get_brightness(star_name, dz) for dz in DIZHI}


def is_temple_or_prosperous(star_name: str, dizhi: str) -> bool:
    """判断星曜是否庙旺 (亮度值 >= 4, 即庙或旺)"""
    return get_brightness_value(star_name, dizhi) >= 4


def is_fallen(star_name: str, dizhi: str) -> bool:
    """判断星曜是否落陷 (亮度值 == 0)"""
    return get_brightness_value(star_name, dizhi) == 0


def load_raw_table() -> dict:
    """返回原始 JSON 数据"""
    return _get_data()


def get_star_system(star_name: str) -> str:
    """返回星曜所属星系: '紫微系' 或 '天府系'"""
    return _get_data()["stars"][star_name]["system"]


def get_star_wuxing(star_name: str) -> str:
    """返回星曜五行属性"""
    return _get_data()["stars"][star_name]["wuxing"]


def print_brightness_table(star_name: str):
    """打印某星的十二宫亮度表 (调试用)"""
    data = _get_data()
    star = data["stars"].get(star_name)
    if not star:
        print(f"未知星曜: {star_name}")
        return
    print(f"\n{star_name} ({star['wuxing']}) — {star['system']}")
    print("| " + " | ".join(DIZHI) + " |")
    print("|" + "|".join(["---" for _ in DIZHI]) + "|")
    print("| " + " | ".join(star["brightness"]) + " |")


def build_star_brightness_matrix(star_names: list[str] = None) -> dict:
    """
    构建 星×地支 亮度矩阵, 方便批量计算
    返回: {"紫微": {"寅": "旺", "卯": "旺", ...}, ...}
    """
    data = _get_data()
    names = star_names or list(data["stars"].keys())
    result = {}
    for name in names:
        star = data["stars"][name]
        result[name] = {DIZHI[i]: star["brightness"][i] for i in range(12)}
    return result


def build_palace_star_matrix() -> dict:
    """
    构建 地支×星 亮度矩阵
    返回: {"寅": {"紫微": "旺", "天机": "旺", ...}, ...}
    """
    data = _get_data()
    result = {}
    for i, dz in enumerate(DIZHI):
        result[dz] = {name: star["brightness"][i] for name, star in data["stars"].items()}
    return result


def classify_palace_by_brightness(dizhi: str) -> dict[str, list]:
    """将某宫位所有星按亮度分类"""
    stars = get_all_stars_in_palace(dizhi)
    result = {k: [] for k in BRIGHTNESS_MAP}
    for name, level in stars.items():
        result[level].append(name)
    return result


if __name__ == "__main__":
    print("=" * 50)
    print("紫微斗数星曜亮度查表模块 v2 — 示例")
    print("=" * 50)
    
    print("\n1. 天府全宫庙:", all(get_brightness("天府", dz) == "庙" for dz in DIZHI))
    
    print("\n2. 单星查询:")
    print(f"   紫微在午: {get_brightness('紫微', '午')} ({get_brightness_value('紫微', '午')})")
    print(f"   贪狼在辰: {get_brightness('贪狼', '辰')} ({get_brightness_value('贪狼', '辰')})")
    print(f"   太阳在子: {get_brightness('太阳', '子')} ({get_brightness_value('太阳', '子')})")
    
    print("\n3. 寅宫分类:")
    for level, stars in classify_palace_by_brightness("寅").items():
        if stars:
            print(f"   {level}: {', '.join(stars)}")
    
    print("\n4. 十二宫总评分:")
    for dz in DIZHI:
        score = get_palace_score(dz)
        bar = "█" * (score // 2) + "." * ((70 - score) // 2)
        print(f"   {dz}: {score:2d}/70 {bar}")
    
    print("\n5. 庙旺星数统计:")
    for dz in DIZHI:
        stars = get_all_stars_in_palace(dz)
        count = sum(1 for v in stars.values() if v in ("庙", "旺"))
        print(f"   {dz}: {count}颗庙旺")

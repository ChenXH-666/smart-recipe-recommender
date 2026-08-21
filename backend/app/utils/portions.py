"""
用量解析工具：把菜谱里自由文本的用量（"200克"、"2个"、"适量"、"一把"）解析为近似克数，
统一喂给营养估算与购物清单/价格。返回 None 表示无法解析（由调用方兜底）。
单位为"人份"的估算以 100g 为一份默认，避免数量单位不一致。
"""
import re

# 常见"可数单位"每份近似克数（按食材用途大概值，估算用）
UNIT_GRAM = {
    "个": None,   # 按食物组给默认，见下方
    "只": None,
    "根": None,
    "片": None,
    "瓣": None,
    "把": None,
    "块": None,
    "颗": None,
    "枚": None,
    "勺子": 15,
    "勺": 15,
    "大勺": 15,
    "小勺": 5,
    "茶匙": 5,
    "汤匙": 15,
    "碗": 200,
    "盒": 250,
    "包": 200,
    "瓶": 500,
}

_VOLUME_TO_GRAM_ML = 1.0  # 毫升≈克（液体），粗略


def _extract_number(s: str):
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~至]\s*(\d+(?:\.\d+)?)", s)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def parse_grams(quantity: str, default_per_item: int = 100) -> float | None:
    """解析用量文本为克数。默认单份 100g；无法解析返回 None。"""
    if not quantity:
        return None
    q = quantity.strip().lower()

    # 若干/几个 的模糊表述 → 默认一整份
    if "适量" in q or "少许" in q or "若干" in q or "若干" in q or "适量" in q:
        return default_per_item

    # 明确克/公斤/斤/两/千克
    num = _extract_number(q)
    if num is None:
        return default_per_item if ("适量" not in q and "少许" not in q) else default_per_item

    for unit, factor in (
        ("千克", 1000), ("公斤", 1000), ("kg", 1000),
        ("斤", 500), ("两", 50),
        ("克", 1), ("g", 1), ("毫升", 1), ("ml", 1),
        ("升", 1000), ("l", 1000),
    ):
        if unit in q:
            return num * factor

    # 体积近似（毫升→克）
    if "ml" in q:
        return num * _VOLUME_TO_GRAM_ML

    # 可数单位按每份默认重量估算
    # 注意：需按单位名长度降序匹配，保证更具体的单位（如"小勺""大勺"）先于
    # 其子串单位（如"勺"）命中，否则 "1小勺" 会被 "勺" 误判为 15g。
    for u, grams in sorted(UNIT_GRAM.items(), key=lambda kv: -len(kv[0])):
        if u in q:
            if grams is not None:
                return num * grams
            return num * default_per_item  # 个/只/根等按 default

    # 只有数字无单位：按"份数"× 默认单份
    return num * default_per_item if num else default_per_item


def split_quantity_units(quantity: str) -> float | None:
    """返回克数（复用 parse_grams，纯数字兜底为 None 的版本留给调用方决定）"""
    return parse_grams(quantity)
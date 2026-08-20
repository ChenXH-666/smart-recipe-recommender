#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为所有菜谱生成本地文字封面图
- 每张图写上对应菜名 + emoji
- 渐变背景，风格统一
- 图片保存在 backend/static/recipe_covers/，URL 写入数据库
- 100% 不会错配，不依赖网络

运行前请确保已安装 Pillow:
    pip install Pillow

运行方式:
    python .\import_data\generate_covers.py
"""
import sys
import os
import logging
import random
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

from app.database import SessionLocal
from app.models import Recipe

# 输出目录
OUTPUT_DIR = project_root / "static" / "recipe_covers"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

IMG_WIDTH = 400
IMG_HEIGHT = 300

# 食物 emoji 映射
EMOJI_MAP = [
    (['鱼', '鲫', '鲤', '鲈', '带鱼', '黄花鱼', '鳕鱼', '三文鱼'], '🐟'),
    (['虾', '虾仁', '虾球', '龙虾'], '🦐'),
    (['蟹', '螃蟹'], '🦀'),
    (['鸡', '鸡腿', '鸡翅', '鸡胸', '鸡爪', '卤鸡'], '🍗'),
    (['鸭', '鹅'], '🦆'),
    (['牛', '牛肉', '牛排', '牛腩', '肥牛'], '🥩'),
    (['羊', '羊肉'], '🍖'),
    (['猪', '猪肉', '排骨', '五花肉', '里脊', '肉'], '🥓'),
    (['蛋', '鸡蛋', '鸭蛋'], '🍳'),
    (['豆腐', '豆干', '腐竹'], '🧈'),
    (['面', '面条', '拉面', '刀削面', '意大利面'], '🍜'),
    (['饭', '米饭', '炒饭', '盖饭', '焖饭'], '🍚'),
    (['饺子', '包子', '馄饨', '水饺', '煎饺'], '🥟'),
    (['饼', '烧饼', '酥饼', '煎饼', '春饼'], '🥞'),
    (['汤', '煲汤', '炖汤', '羹'], '🍲'),
    (['沙拉', '凉菜', '拌菜'], '🥗'),
    (['蛋糕', '面包', '甜点', '饼干'], '🍰'),
    (['土豆', '马铃薯'], '🥔'),
    (['西红柿', '番茄'], '🍅'),
    (['茄子'], '🍆'),
    (['胡萝卜'], '🥕'),
    (['玉米'], '🌽'),
    (['蘑菇', '香菇', '金针菇', '木耳'], '🍄'),
    (['辣椒', '青椒', '红椒', '尖椒'], '🌶️'),
    (['黄瓜', '冬瓜', '丝瓜', '苦瓜', '南瓜'], '🥒'),
    (['白菜', '青菜', '菠菜', '生菜', '油菜', '菜心'], '🥬'),
    (['苹果', '香蕉', '橙子', '水果'], '🍎'),
    (['咖啡', '奶茶'], '☕'),
]

# 渐变配色
GRADIENTS = [
    ((255, 154, 158), (250, 208, 196)),  # 粉红
    ((255, 183, 107), (255, 134, 102)),  # 橙红
    ((255, 175, 123), (255, 210, 170)),  # 暖橙
    ((129, 207, 164), (176, 227, 196)),  # 浅绿
    ((161, 209, 154), (217, 238, 199)),  # 嫩绿
    ((79, 172, 154), (149, 211, 199)),   # 青绿
    ((254, 225, 64), (255, 247, 153)),   # 明黄
    ((248, 202, 0), (255, 234, 130)),    # 金黄
    ((140, 160, 227), (200, 213, 245)),  # 淡蓝
    ((174, 148, 214), (220, 208, 240)),  # 淡紫
    ((210, 167, 117), (238, 212, 182)),  # 棕褐
    ((193, 143, 100), (222, 186, 152)),  # 咖啡
    ((118, 139, 176), (173, 192, 220)),  # 灰蓝
]


def get_emoji(title: str) -> str:
    """根据菜名关键词匹配 emoji"""
    for keywords, emoji in EMOJI_MAP:
        if any(kw in title for kw in keywords):
            return emoji
    return '🍽️'


def get_gradient(title: str) -> tuple:
    """根据菜名哈希选择配色，保证同一道菜颜色一致"""
    idx = hash(title) % len(GRADIENTS)
    return GRADIENTS[idx]


def create_gradient(width: int, height: int, color_top: tuple, color_bottom: tuple):
    """绘制渐变色背景"""
    from PIL import Image, ImageDraw
    base = Image.new('RGB', (width, height), color_top)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        ratio = y / height
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return base


def generate_image(title: str, output_path: str):
    """生成单张文字封面图"""
    from PIL import Image, ImageDraw, ImageFont

    color_top, color_bottom = get_gradient(title)
    img = create_gradient(IMG_WIDTH, IMG_HEIGHT, color_top, color_bottom)
    draw = ImageDraw.Draw(img)

    emoji = get_emoji(title)

    # 字体大小
    emoji_size = 64
    text_size = 34

    # 加载字体
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyh.ttf",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    emoji_font = None
    text_font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                text_font = ImageFont.truetype(fp, text_size)
                emoji_font = ImageFont.truetype(fp, emoji_size)
                break
            except:
                continue
    if text_font is None:
        text_font = ImageFont.load_default()
        emoji_font = text_font

    # 计算位置，整体垂直居中
    bbox_emoji = draw.textbbox((0, 0), emoji, font=emoji_font)
    emoji_w = bbox_emoji[2] - bbox_emoji[0]
    emoji_h = bbox_emoji[3] - bbox_emoji[1]

    bbox_text = draw.textbbox((0, 0), title, font=text_font)
    text_w = bbox_text[2] - bbox_text[0]
    text_h = bbox_text[3] - bbox_text[1]

    total_h = emoji_h + 20 + text_h
    start_y = (IMG_HEIGHT - total_h) // 2

    emoji_x = (IMG_WIDTH - emoji_w) // 2
    text_x = (IMG_WIDTH - text_w) // 2
    text_y = start_y + emoji_h + 20

    # 绘制阴影
    draw.text((emoji_x + 2, start_y + 2), emoji, fill=(0, 0, 0), font=emoji_font)
    draw.text((text_x + 2, text_y + 2), title, fill=(0, 0, 0), font=text_font)

    # 绘制主内容
    draw.text((emoji_x, start_y), emoji, fill=(255, 255, 255), font=emoji_font)
    draw.text((text_x, text_y), title, fill=(255, 255, 255), font=text_font)

    img.save(output_path, 'JPEG', quality=90)


def generate_default_cover():
    """生成默认封面图"""
    from PIL import Image, ImageDraw, ImageFont
    color_top, color_bottom = ((255, 154, 158), (250, 208, 196))
    img = create_gradient(IMG_WIDTH, IMG_HEIGHT, color_top, color_bottom)
    draw = ImageDraw.Draw(img)

    text = "美食菜谱"
    font = None
    for fp in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf"]:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 40)
                break
            except:
                continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    x = (IMG_WIDTH - (bbox[2] - bbox[0])) // 2
    y = (IMG_HEIGHT - (bbox[3] - bbox[1])) // 2
    draw.text((x, y), text, fill=(255, 255, 255), font=font)
    img.save(OUTPUT_DIR / "default.jpg", 'JPEG', quality=90)


def generate_all():
    db = SessionLocal()
    try:
        recipes = db.query(Recipe).filter(
            Recipe.is_deleted == 0,
            Recipe.status == "approved"
        ).all()

        print(f"总菜谱数: {len(recipes)}")
        print(f"输出目录: {OUTPUT_DIR}")
        print("=" * 60)

        generate_default_cover()

        success = 0
        for idx, recipe in enumerate(recipes, 1):
            title = recipe.title.strip() if recipe.title else "未命名菜谱"
            filename = f"recipe_{recipe.id}.jpg"
            filepath = OUTPUT_DIR / filename

            try:
                generate_image(title, str(filepath))
                recipe.cover_image_url = f"/static/recipe_covers/{filename}"
                success += 1

                if idx % 500 == 0:
                    db.commit()
                    print(f"已生成 {idx}/{len(recipes)} 张...")
            except Exception as e:
                print(f"  ⚠️  {title} 生成失败: {e}")

        db.commit()
        print("=" * 60)
        print(f"✅ 完成！成功生成 {success}/{len(recipes)} 张封面图")
        print(f"图片目录: {OUTPUT_DIR}")

    except Exception as e:
        print(f"错误: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    confirm = input("确定要为所有菜谱生成本地文字封面图吗？(输入y确认): ")
    if confirm.lower() == 'y':
        generate_all()
    else:
        print("已取消")

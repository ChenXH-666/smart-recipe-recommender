#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为所有套餐(MealPlan)生成文字封面图（风格与菜谱封面一致）
- 输出到 backend/static/meal_plan_covers/meal_plan_{id}.jpg
- 回写 meal_plan.cover_image_url
运行: conda activate food && python .\import_data\generate_meal_plan_covers.py
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.database import SessionLocal
from app.models import MealPlan
from generate_covers import generate_image, IMG_WIDTH, IMG_HEIGHT, create_gradient

OUT_DIR = project_root / "static" / "meal_plan_covers"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    db = SessionLocal()
    try:
        plans = db.query(MealPlan).filter(MealPlan.is_deleted == 0).all()
        done = 0
        for plan in plans:
            title = (plan.title or "美食套餐").strip()
            filename = f"meal_plan_{plan.id}.jpg"
            filepath = OUT_DIR / filename
            try:
                generate_image(title, str(filepath))
                plan.cover_image_url = f"/static/meal_plan_covers/{filename}"
                done += 1
            except Exception as e:
                print(f"  x id={plan.id} {title} 失败: {e}")
        db.commit()
        print(f"完成：生成套餐封面 {done}/{len(plans)} 张 -> {OUT_DIR}")
    except Exception as e:
        db.rollback()
        print(f"错误: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
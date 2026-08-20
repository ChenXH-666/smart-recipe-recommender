#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
菜谱数据导入脚本
从 new_data/05_insert/ 目录读取所有 JSONL 文件并导入到数据库
（数据已经过 process_recipes.py 预处理，tag_id 和 ingredient_id 已映射为数据库实际 ID）
"""

import json
import sys
from pathlib import Path

# 添加项目根目录（backend/）到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import (
    User, Tag, Recipe, RecipeTag, Ingredient,
    RecipeIngredient, RecipeStep
)


def get_or_create_user(db: Session, user_id: int, username: str = None, nickname: str = None):
    """获取或创建用户（如果用户不存在，创建一个临时用户）"""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        return user

    username = username or f"user_{user_id}"
    email = f"user_{user_id}@example.com"
    user = User(
        id=user_id,
        username=username,
        nickname=nickname,
        email=email,
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyWw5z5z5z5",
        role="user",
        is_active=1
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def import_single_recipe(db: Session, recipe_data: dict):
    """导入单个菜谱（新格式：tag_id/ingredient_id 已解析为数据库 ID）"""
    recipe_info = recipe_data["recipe"]
    tags_data = recipe_data["tags"]
    ingredients_data = recipe_data["ingredients"]
    steps_data = recipe_data["steps"]

    # 1. 处理作者
    author = get_or_create_user(db, recipe_info["author_id"])

    # 2. 创建菜谱（id、created_at、updated_at 由数据库自动生成）
    recipe = Recipe(
        title=recipe_info["title"],
        description=recipe_info.get("description"),
        cover_image_url=recipe_info.get("cover_image_url"),
        difficulty=recipe_info.get("difficulty"),
        cooking_time=recipe_info.get("cooking_time"),
        servings=recipe_info.get("servings"),
        estimated_cost=recipe_info.get("estimated_cost"),
        author_id=author.id,
        status=recipe_info.get("status", "approved"),
        view_count=recipe_info.get("view_count", 0),
        favorite_count=recipe_info.get("favorite_count", 0)
    )
    db.add(recipe)
    db.flush()  # 获取 auto-increment id

    # 3. 处理标签（tag_id 已解析，直接查询）
    for tag_data in tags_data:
        tag = db.query(Tag).filter(Tag.id == tag_data["tag_id"]).first()
        if tag is None:
            print(f"  警告：标签 ID {tag_data['tag_id']} ({tag_data.get('tag_name')}) 不存在，跳过")
            continue
        recipe_tag = RecipeTag(recipe_id=recipe.id, tag_id=tag.id)
        db.add(recipe_tag)

    # 4. 处理食材（ingredient_id 已解析，直接查询）
    for ingr_data in ingredients_data:
        ingredient = db.query(Ingredient).filter(Ingredient.id == ingr_data["ingredient_id"]).first()
        if ingredient is None:
            print(f"  警告：食材 ID {ingr_data['ingredient_id']} ({ingr_data.get('ingredient_name')}) 不存在，跳过")
            continue
        recipe_ingr = RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_id=ingredient.id,
            quantity=ingr_data.get("quantity"),
            note=ingr_data.get("note"),
            sort_order=ingr_data.get("sort_order", 0)
        )
        db.add(recipe_ingr)

    # 5. 处理步骤
    for step_data in steps_data:
        step = RecipeStep(
            recipe_id=recipe.id,
            step_number=step_data["step_number"],
            instruction=step_data["instruction"],
            # image_url=step_data.get("image_url"),  # 步骤图片功能，暂不启用
            duration=step_data.get("duration")
        )
        db.add(step)

    db.commit()
    return recipe


def clear_existing_data(db: Session):
    """清空菜谱相关表（RecipeTag → RecipeIngredient → RecipeStep → Recipe）"""
    from app.models import RecipeTag, RecipeIngredient, RecipeStep, Recipe
    tables = [RecipeTag, RecipeIngredient, RecipeStep, Recipe]
    for table in tables:
        deleted = db.query(table).delete()
        print(f"  清空 {table.__tablename__}: {deleted} 条")
    db.commit()
    print("[OK] 菜谱相关表已清空")


def import_all_recipes(data_dir: str = "../new_data/05_insert"):
    """导入所有菜谱数据"""
    db = SessionLocal()
    try:
        # 确保数据目录存在
        data_path = Path(data_dir)
        if not data_path.exists():
            data_path = project_root.parent / "new_data" / "05_insert"

        if not data_path.exists():
            print(f"错误：数据目录不存在: {data_path}")
            return

        # 清空现有数据
        print("=" * 50)
        print("清空菜谱相关表...")
        print("=" * 50)
        clear_existing_data(db)

        # 获取所有 jsonl 文件
        jsonl_files = sorted(data_path.glob("*.jsonl"))
        print(f"\n找到 {len(jsonl_files)} 个文件\n")

        total_recipes = 0
        for file_path in jsonl_files:
            print(f"正在处理: {file_path.name}")
            file_recipes = 0
            with open(file_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        line = line.strip()
                        if not line:
                            continue
                        recipe_data = json.loads(line)
                        import_single_recipe(db, recipe_data)
                        file_recipes += 1
                        total_recipes += 1
                        if file_recipes % 100 == 0:
                            print(f"  已处理 {file_recipes} 条...")
                    except Exception as e:
                        print(f"  错误：第 {line_num} 行: {e}")
                        db.rollback()
            print(f"  {file_path.name} 完成，导入 {file_recipes} 条")

        print(f"\n{'=' * 50}")
        print(f"全部完成！共导入 {total_recipes} 条菜谱")
        print(f"{'=' * 50}")

    except Exception as e:
        print(f"发生错误: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("开始导入菜谱数据...")
    import_all_recipes()
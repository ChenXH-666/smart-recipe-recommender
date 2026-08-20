#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
套餐数据导入脚本
从 new_data/07_meal_plans/ 目录读取 JSONL 文件并导入到数据库

数据文件：
  - meal_plans.jsonl      → 套餐主表（120条）
  - meal_plan_items.jsonl → 套餐明细表（372条）

前置条件：
  1. 数据库已初始化（init.sql 已执行）
  2. 菜谱数据已导入（import_recipes.py 已运行），因为明细中的 recipe_id 需要引用 recipes 表
  3. meal_plans.jsonl 编码问题已修复（必须为合法 UTF-8）
  4. meal_plan_items.jsonl 中唯一键冲突已处理
"""

import json
import sys
from pathlib import Path

# 添加项目根目录（backend/）到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, MealPlan, MealPlanItem, Recipe


def get_official_user(db: Session) -> User:
    """获取系统官方账号（官方小厨），不存在则创建一个。"""
    user = db.query(User).filter(
        (User.username == "admin") | (User.nickname == "官方小厨")
    ).first()
    if user:
        return user

    user = User(
        username="admin",
        nickname="官方小厨",
        email="admin@recipe.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyWw5z5z5z5",
        role="admin",
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _is_nameless_user(user: User) -> bool:
    """判断用户是否属于“没有写名字”的占位账号。"""
    if not user:
        return True
    if not user.nickname or not user.nickname.strip():
        return True
    # 旧脚本生成的占位用户：username 为 user_<id> 且 nickname 与 username 相同
    if user.username and user.username.startswith("user_") and user.username == user.nickname:
        return True
    return False


def resolve_meal_plan_user(db: Session, user_id: int) -> User:
    """
    解析套餐的创建者。
    - 如果用户存在且有真实昵称，直接返回该用户。
    - 如果用户不存在、没写名字、或是旧占位账号，则统一归到官方小厨。
    """
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if not _is_nameless_user(user):
        return user
    return get_official_user(db)


def clear_existing_data(db: Session):
    """
    清空套餐相关表（先删明细，再删主表，避免外键约束冲突）。
    注意：这里不需要清空 recipes 表，因为套餐数据依赖菜谱数据。
    """
    items_deleted = db.query(MealPlanItem).delete()
    print(f"  清空 meal_plan_items: {items_deleted} 条")

    plans_deleted = db.query(MealPlan).delete()
    print(f"  清空 meal_plans: {plans_deleted} 条")

    db.commit()
    print("[OK] 套餐相关表已清空")


def import_meal_plans(db: Session, plans_file: Path) -> dict:
    """
    导入套餐主表数据。
    返回 {原始id: 数据库实际id} 的映射，供明细导入时使用。
    """
    print(f"\n正在导入套餐主表: {plans_file.name}")

    id_mapping = {}  # 原始id → 数据库实际id
    count = 0
    errors = 0

    with open(plans_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  [跳过] 第{line_num}行 JSON 解析失败: {e}")
                errors += 1
                continue

            # 解析套餐创建者：无名字/不存在的用户统一归到官方小厨
            user = resolve_meal_plan_user(db, data["user_id"])

            # reviewer_id 也需要用户存在，缺失或无效时同样归到官方小厨
            reviewer_id = data.get("reviewer_id")
            if reviewer_id:
                reviewer = resolve_meal_plan_user(db, reviewer_id)
                reviewer_id = reviewer.id

            plan = MealPlan(
                user_id=user.id,
                title=data["title"],
                description=data.get("description"),
                cover_image_url=data.get("cover_image_url"),
                is_public=data.get("is_public", 1),
                status=data.get("status", "approved"),
                reviewer_id=reviewer_id,
                review_comment=data.get("review_comment"),
                reviewed_at=data.get("reviewed_at"),
                is_deleted=data.get("is_deleted", 0),
                favorite_count=data.get("favorite_count", 0),
                view_count=data.get("view_count", 0),
                # created_at / updated_at 由数据库自动生成
            )
            db.add(plan)
            db.flush()  # 获取 auto-increment id

            id_mapping[data["id"]] = plan.id
            count += 1

            if count % 20 == 0:
                print(f"  已导入 {count} 条套餐...")

    db.commit()
    print(f"[OK] 套餐主表导入完成: 成功 {count} 条, 失败 {errors} 条")
    return id_mapping


def import_meal_plan_items(db: Session, items_file: Path, id_mapping: dict) -> None:
    """
    导入套餐明细数据。
    使用 id_mapping 将原始 meal_plan_id 映射到数据库实际 id。
    """
    print(f"\n正在导入套餐明细: {items_file.name}")

    # 预加载所有已导入的 recipe_id，用于校验
    existing_recipes = set(
        r[0] for r in db.query(Recipe.id).all()
    )

    count = 0
    skipped = 0
    errors = 0
    seen_pairs = set()  # 用于去重 (meal_plan_id, recipe_id)

    with open(items_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  [跳过] 第{line_num}行 JSON 解析失败: {e}")
                errors += 1
                continue

            original_plan_id = data["meal_plan_id"]
            recipe_id = data["recipe_id"]

            # 映射套餐ID
            db_plan_id = id_mapping.get(original_plan_id)
            if db_plan_id is None:
                print(f"  [跳过] 第{line_num}行: 套餐ID {original_plan_id} 未在主表中找到")
                skipped += 1
                continue

            # 校验 recipe_id 是否存在
            if recipe_id not in existing_recipes:
                print(f"  [跳过] 第{line_num}行: 食谱ID {recipe_id} 在 recipes 表中不存在")
                skipped += 1
                continue

            # 去重：跳过 (meal_plan_id, recipe_id) 重复的记录
            pair = (db_plan_id, recipe_id)
            if pair in seen_pairs:
                print(f"  [去重] 第{line_num}行: (meal_plan_id={original_plan_id}, recipe_id={recipe_id}) 重复，跳过")
                skipped += 1
                continue
            seen_pairs.add(pair)

            item = MealPlanItem(
                meal_plan_id=db_plan_id,
                recipe_id=recipe_id,
                sort_order=data.get("sort_order", 0),
                note=data.get("note"),
            )
            db.add(item)
            count += 1

            if count % 50 == 0:
                print(f"  已导入 {count} 条明细...")

    db.commit()
    print(f"[OK] 套餐明细导入完成: 成功 {count} 条, 跳过 {skipped} 条, 失败 {errors} 条")


def import_all(data_dir: str = None):
    """导入全部套餐数据"""
    db = SessionLocal()
    try:
        # 确定数据目录
        if data_dir:
            data_path = Path(data_dir)
        else:
            data_path = project_root.parent / "new_data" / "07_meal_plans"

        if not data_path.exists():
            print(f"错误：数据目录不存在: {data_path}")
            return

        plans_file = data_path / "meal_plans.jsonl"
        items_file = data_path / "meal_plan_items.jsonl"

        if not plans_file.exists():
            print(f"错误：套餐主表文件不存在: {plans_file}")
            return
        if not items_file.exists():
            print(f"错误：套餐明细文件不存在: {items_file}")
            return

        # 1. 清空现有数据
        print("=" * 60)
        print("清空套餐相关表...")
        print("=" * 60)
        clear_existing_data(db)

        # 2. 导入套餐主表
        print("\n" + "=" * 60)
        print("导入套餐主表...")
        print("=" * 60)
        id_mapping = import_meal_plans(db, plans_file)

        # 3. 导入套餐明细
        print("\n" + "=" * 60)
        print("导入套餐明细...")
        print("=" * 60)
        import_meal_plan_items(db, items_file, id_mapping)

        # 4. 统计
        plan_count = db.query(MealPlan).count()
        item_count = db.query(MealPlanItem).count()
        print(f"\n{'=' * 60}")
        print(f"全部完成！")
        print(f"  meal_plans:      {plan_count} 条")
        print(f"  meal_plan_items: {item_count} 条")
        print(f"{'=' * 60}")

    except Exception as e:
        print(f"\n发生错误: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("开始导入套餐数据...")
    import_all()

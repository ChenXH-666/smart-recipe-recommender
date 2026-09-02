"""
基础数据导入脚本
- 用户表 users (插入系统用户)
- 标签表 tags (从 tags.txt 导入，JSON格式)
- 食材表 ingredients (从 new_ingredients.txt 导入，JSON格式)
"""

import sys
import json
from pathlib import Path
from typing import List

# 添加项目根目录（backend/）到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, Tag, Ingredient
from app.core.security import hash_password


def import_tags(db: Session, tags_file: Path) -> int:
    """从文件导入标签（JSON格式）"""
    if not tags_file.exists():
        print(f"警告：标签文件不存在: {tags_file}")
        return 0

    count = 0
    with open(tags_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                # 解析JSON
                tag_data = json.loads(line)
                tag_name = tag_data.get("name")
                tag_type = tag_data.get("type")
                tag_desc = tag_data.get("description")
                
                if not tag_name:
                    continue

                # 检查标签是否已存在
                existing = db.query(Tag).filter(Tag.name == tag_name).first()
                if existing:
                    continue

                # 创建标签
                tag = Tag(name=tag_name, type=tag_type, description=tag_desc)
                db.add(tag)
                count += 1
            except Exception as e:
                print(f"  跳过无效行: {line[:50]}... 错误: {e}")
                continue

    db.commit()
    print(f"[OK] 导入标签: {count} 条")
    return count


def import_ingredients(db: Session, ingredients_file: Path) -> int:
    """从文件导入食材（JSON格式）

    导入的食材归属官方账号（admin/官方小厨），status 走模型默认 approved；
    submitted_by 记录官方账号 ID，与"平台预置食材归官方小厨"的现有数据一致。
    """
    if not ingredients_file.exists():
        print(f"警告：食材文件不存在: {ingredients_file}")
        return 0

    # 查询官方账号（可能尚未创建时为 None，此时 submitted_by 留空）
    official = db.query(User).filter(User.username == "admin").first()
    official_id = official.id if official else None

    count = 0
    with open(ingredients_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                # 解析JSON
                ingr_data = json.loads(line)
                ingr_name = ingr_data.get("name")
                ingr_category = ingr_data.get("category")
                
                if not ingr_name:
                    continue

                # 检查食材是否已存在
                existing = db.query(Ingredient).filter(Ingredient.name == ingr_name).first()
                if existing:
                    continue

                # 创建食材
                ingredient = Ingredient(name=ingr_name, category=ingr_category, submitted_by=official_id)
                db.add(ingredient)
                count += 1
            except Exception as e:
                print(f"  跳过无效行: {line[:50]}... 错误: {e}")
                continue

    db.commit()
    print(f"[OK] 导入食材: {count} 条")
    return count


def create_sample_users(db: Session) -> int:
    """创建系统用户（官方账号 + 内测用户）"""
    sample_users = [
        {
            "username": "admin",
            "nickname": "官方小厨",
            "email": "admin@recipe.com",
            "password": "admin123",
            "role": "admin",
            "avatar_url": None
        },
        {
            "username": "tester",
            "nickname": "内测达人",
            "email": "tester@recipe.com",
            "password": "test123",
            "role": "user",
            "avatar_url": None
        }
    ]

    count = 0
    for user_data in sample_users:
        # 检查用户是否已存在
        existing = db.query(User).filter(
            (User.username == user_data["username"]) | (User.email == user_data["email"])
        ).first()
        if existing:
            print(f"  用户已存在: {user_data['username']}")
            continue

        # 创建用户
        user = User(
            username=user_data["username"],
            nickname=user_data.get("nickname"),
            email=user_data["email"],
            password_hash=hash_password(user_data["password"]),
            role=user_data["role"],
            avatar_url=user_data["avatar_url"],
            is_active=1
        )
        db.add(user)
        count += 1
        print(f"  创建用户: {user_data['username']} ({user_data['nickname']})")

    db.commit()
    print(f"[OK] 创建用户: {count} 条")
    return count


def import_all_basic_data():
    """导入所有基础数据"""
    db = SessionLocal()
    try:
        print("=" * 50)
        print("开始导入基础数据...")
        print("=" * 50)

        # 清空现有数据
        from app.models import RecipeTag, RecipeIngredient, RecipeStep, Recipe
        print("\n[0/3] 清空现有数据...")
        tables_to_clear = [RecipeTag, RecipeIngredient, RecipeStep, Recipe, Ingredient, Tag, User]
        for table in tables_to_clear:
            deleted = db.query(table).delete()
            print(f"  清空 {table.__tablename__}: {deleted} 条")
        db.commit()

        # 1. 创建示例用户
        print("\n[1/3] 导入用户表...")
        create_sample_users(db)

        # 2. 导入标签
        print("\n[2/3] 导入标签表...")
        tags_file = project_root / "../new_data/fields/tags.txt"
        import_tags(db, tags_file)

        # 3. 导入食材
        print("\n[3/3] 导入食材表...")
        ingredients_file = project_root / "../new_data/fields/new_ingredients.txt"
        import_ingredients(db, ingredients_file)

        # 统计数据
        user_count = db.query(User).count()
        tag_count = db.query(Tag).count()
        ingredient_count = db.query(Ingredient).count()

        print("\n" + "=" * 50)
        print("基础数据导入完成！")
        print(f"  用户总数: {user_count}")
        print(f"  标签总数: {tag_count}")
        print(f"  食材总数: {ingredient_count}")
        print("=" * 50)

    except Exception as e:
        print(f"\n发生错误: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import_all_basic_data()
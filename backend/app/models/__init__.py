"""
所有 SQLAlchemy 数据库模型 —— 严格按 database_design.md 定义

============================================================================
                         数据模型总体设计（面向答辩说明）
============================================================================

本系统围绕"菜谱推荐与套餐规划"核心业务，将数据模型划分为四大模块：

  【用户模块】User —— 用户账户、角色、权限
  【菜谱模块】Recipe / Tag / Ingredient —— 菜谱本身及其元数据（标签、食材、步骤）
  【互动模块】UserFavorite / UserBrowseHistory / RecipeReview / CookingNote —— 收藏、浏览、点评、心得
  【AI模块】  MealPlan / MealPlanItem / AiConversation / AiMessage —— 套餐规划、AI对话

设计原则：
  1. 多对多关系通过关联表（RecipeTag, RecipeIngredient）显式建模，便于查询扩展
  2. 审核工作流：Recipe 和 MealPlan 都有 status 字段（draft→pending→approved/rejected）
  3. 软删除策略：is_deleted 字段，避免物理删除导致数据丢失
  4. 外键约束：ondelete="CASCADE" 用于强关联；ondelete="SET NULL" 用于弱关联（如作者/审核人）
"""

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum, ForeignKey,
    DECIMAL, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║                          【用户模块】用户与权限                              ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class User(Base):
    """用户表 —— 系统所有角色的基表（普通用户 / 管理员统一存储）"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    nickname = Column(String(50), nullable=True, comment="显示昵称，用于菜谱作者等展示场景")
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    role = Column(Enum("user", "admin"), nullable=False, default="user")
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    # 个性化偏好（JSON）：cuisines(标签)/diet_tags(忌口过敏)/free_text(自由文本)
    preferences = Column(JSON, nullable=True, comment="用户个性化偏好")

    # 关系
    favorites = relationship("UserFavorite", back_populates="user", cascade="all, delete-orphan")
    browse_history = relationship("UserBrowseHistory", back_populates="user", cascade="all, delete-orphan")
    recipes = relationship("Recipe", back_populates="author", foreign_keys="Recipe.author_id")
    reviews = relationship("RecipeReview", back_populates="user", cascade="all, delete-orphan")
    cooking_notes = relationship("CookingNote", back_populates="user", cascade="all, delete-orphan")
    cooking_note_comments = relationship("CookingNoteComment", back_populates="user", cascade="all, delete-orphan")
    meal_plans = relationship("MealPlan", back_populates="creator", foreign_keys="MealPlan.user_id")
    conversations = relationship("AiConversation", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("uk_username", "username"),
        Index("uk_email", "email"),
    )


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║                          【菜谱模块】菜谱与元数据                            ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class Tag(Base):
    """标签表 —— 通过 type 区分用途：cuisine(菜系), taste(口味), meal_type(餐次), difficulty 等"""
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    type = Column(String(50), nullable=True)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    recipe_tags = relationship("RecipeTag", back_populates="tag", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("name", "type", name="uk_name_type"),
        Index("idx_type", "type"),
    )


class Recipe(Base):
    """
    菜谱表 —— 核心业务实体

    审核工作流：
      draft(草稿) → pending(待审核) → approved(已通过) / rejected(已驳回)
    管理员创建直接 approved，普通用户创建进入 pending。
    """
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    cover_image_url = Column(String(500), nullable=True)
    difficulty = Column(Enum("easy", "medium", "hard"), nullable=True)
    cooking_time = Column(Integer, nullable=True)
    servings = Column(Integer, nullable=True)
    estimated_cost = Column(DECIMAL(10, 2), nullable=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(Enum("draft", "pending", "approved", "rejected"), nullable=False, default="pending")
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_comment = Column(String(500), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    is_deleted = Column(Integer, nullable=False, default=0)
    view_count = Column(Integer, nullable=False, default=0)
    favorite_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # 关系
    author = relationship("User", back_populates="recipes", foreign_keys=[author_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    tags = relationship("RecipeTag", back_populates="recipe", cascade="all, delete-orphan")
    ingredients = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")
    steps = relationship("RecipeStep", back_populates="recipe", cascade="all, delete-orphan")
    reviews = relationship("RecipeReview", back_populates="recipe", cascade="all, delete-orphan")
    cooking_notes = relationship("CookingNote", back_populates="recipe")
    meal_plan_items = relationship("MealPlanItem", back_populates="recipe", cascade="all, delete-orphan")

    @property
    def author_nickname(self) -> str | None:
        """
        获取作者展示名称 —— 优先显示 nickname，无昵称时回退到 username。
        这是一个计算属性（@property），不会存入数据库，专用于 API 序列化输出。
        注意：必须放在所有 relationship 定义之后，否则 author 属性不可用。
        """
        if self.author:
            return self.author.nickname or self.author.username
        return None

    __table_args__ = (
        # 注意：author_id 和 reviewer_id 已由 ForeignKey 自动创建索引，
        # 此处不再重复声明 fk_recipes_author / fk_recipes_reviewer
        Index("idx_status", "status"),
        Index("idx_author_id", "author_id"),
        Index("idx_created_at", "created_at"),
        Index("idx_estimated_cost", "estimated_cost"),
    )


class RecipeTag(Base):
    """菜谱-标签关联表（多对多）"""
    __tablename__ = "recipe_tags"

    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    recipe = relationship("Recipe", back_populates="tags")
    tag = relationship("Tag", back_populates="recipe_tags")


class Ingredient(Base):
    """食材基础表 —— 独立于菜谱的食材字典，避免食材名称冗余"""
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    category = Column(String(50), nullable=True)
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # ---- 营养与忌口扩展示段（由计算脚本回填，用于估算营养、过敏原/忌口过滤）----
    food_group = Column(String(50), nullable=True, comment="食物组（用于营养平均值兜底）")
    nutrition = Column(JSON, nullable=True, comment="每100g 估算营养 {kcal, protein, fat, carbs}")
    diet_tags = Column(JSON, nullable=True, comment="忌口/过敏原标签，如 [seafood, spicy, gluten, vegetarian]")

    recipe_ingredients = relationship("RecipeIngredient", back_populates="ingredient", cascade="all, delete-orphan")


class RecipeIngredient(Base):
    """菜谱-食材关联表 —— 记录每个菜谱中每种食材的用量和备注"""
    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(String(50), nullable=True)
    note = Column(String(255), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    recipe = relationship("Recipe", back_populates="ingredients")
    ingredient = relationship("Ingredient", back_populates="recipe_ingredients")

    __table_args__ = (
        Index("idx_recipe_id", "recipe_id"),
        Index("idx_ingredient_id", "ingredient_id"),
    )


class RecipeStep(Base):
    """菜谱步骤表 —— 按 step_number 排序，支持配图和预估时长"""
    __tablename__ = "recipe_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)
    step_number = Column(Integer, nullable=False)
    instruction = Column(Text, nullable=False)
    # image_url = Column(String(500), nullable=True)  # 步骤图片功能，暂不启用
    duration = Column(Integer, nullable=True)

    recipe = relationship("Recipe", back_populates="steps")

    __table_args__ = (
        Index("idx_recipe_id_step", "recipe_id"),
    )


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║                     【互动模块】收藏 / 浏览 / 点评 / 心得                     ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class UserFavorite(Base):
    """
    用户收藏表 —— 通过 favorite_type 多态关联 recipe 或 meal_plan。
    设计选择：不用外键到两张表，而是用 type+id 组合，灵活但需业务层校验。
    """
    __tablename__ = "user_favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    favorite_type = Column(Enum("recipe", "meal_plan"), nullable=False)
    favorite_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    user = relationship("User", back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("user_id", "favorite_type", "favorite_id", name="uk_user_fav"),
        Index("idx_favorite", "favorite_type", "favorite_id"),
    )


class UserBrowseHistory(Base):
    """浏览历史表 —— 记录用户浏览菜谱/套餐的时间线，用于个性化推荐

    并发设计：单用户单对象只保留一条记录（"查→有则更新时间，无则插入"的
    upsert 由业务层实现）。但纯应用层去重在并发下有竞态：同一用户双击
    卡片产生的两个并发请求都查到"无记录"而各自插入，产生重复行。
    因此数据库层加 (user_id, recipe_id)/(user_id, meal_plan_id) 两个唯一
    索引兜底——MySQL/SQLite 的唯一索引中 NULL 不参与唯一性判断，天然适配
    recipe_id/meal_plan_id 二选一可空的场景；并发插入冲突由业务层捕获
    IntegrityError 后转为更新（见 utils/browse_history.py）。
    """
    __tablename__ = "user_browse_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True)
    meal_plan_id = Column(Integer, nullable=True)
    viewed_at = Column(DateTime, nullable=False, server_default=func.now())

    user = relationship("User", back_populates="browse_history")
    recipe = relationship("Recipe")

    __table_args__ = (
        UniqueConstraint("user_id", "recipe_id", name="uk_hist_user_recipe"),
        UniqueConstraint("user_id", "meal_plan_id", name="uk_hist_user_plan"),
        Index("idx_user_id", "user_id"),
        Index("idx_viewed_at", "viewed_at"),
    )


class RecipeReview(Base):
    """菜谱点评表 —— 评分+文字评论，支持软删除，已删除内容对非作者不可见"""
    __tablename__ = "recipe_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=True)
    content = Column(Text, nullable=True)
    is_deleted = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    recipe = relationship("Recipe", back_populates="reviews")
    user = relationship("User", back_populates="reviews")


class CookingNote(Base):
    """烹饪心得表 —— 用户分享烹饪体验，可关联菜谱，支持图片集（JSON数组）"""
    __tablename__ = "cooking_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    related_recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True)
    images = Column(JSON, nullable=True)
    is_public = Column(Integer, nullable=False, default=1)
    is_deleted = Column(Integer, nullable=False, default=0)
    view_count = Column(Integer, nullable=False, default=0)
    comment_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="cooking_notes")
    recipe = relationship("Recipe", back_populates="cooking_notes")
    comments = relationship("CookingNoteComment", back_populates="note", cascade="all, delete-orphan")


class CookingNoteComment(Base):
    """心得评论表 —— 针对烹饪心得的文字评论，支持软删除"""
    __tablename__ = "cooking_note_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(Integer, ForeignKey("cooking_notes.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    is_deleted = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    note = relationship("CookingNote", back_populates="comments")
    user = relationship("User", back_populates="cooking_note_comments")


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║                   【AI模块】套餐规划 / AI 对话                               ║
# ╚════════════════════════════════════════════════════════════════════════════╝

class MealPlan(Base):
    """
    套餐表 —— 将多道菜谱组合成一个套餐（菜单规划）。
    审核流程与 Recipe 一致：draft → pending → approved/rejected。
    """
    __tablename__ = "meal_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    cover_image_url = Column(String(500), nullable=True)
    is_public = Column(Integer, nullable=False, default=1)
    status = Column(Enum("draft", "pending", "approved", "rejected"), nullable=False, default="pending")
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_comment = Column(String(500), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    is_deleted = Column(Integer, nullable=False, default=0)
    favorite_count = Column(Integer, nullable=False, default=0)
    view_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    creator = relationship("User", back_populates="meal_plans", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    items = relationship("MealPlanItem", back_populates="meal_plan", cascade="all, delete-orphan")

    @property
    def author_nickname(self) -> str | None:
        """
        获取套餐创建者展示名称 —— 优先显示 nickname，无昵称时回退到 username。
        这是一个计算属性（@property），不会存入数据库，专用于 API 序列化输出。
        """
        if self.creator:
            return self.creator.nickname or self.creator.username
        return None

    __table_args__ = (
        Index("idx_mp_user_id", "user_id"),
        Index("idx_mp_status", "status"),
    )


class MealPlanItem(Base):
    """套餐明细表 —— 套餐与菜谱的多对多关系，附带排序和备注"""
    __tablename__ = "meal_plan_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meal_plan_id = Column(Integer, ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    note = Column(String(255), nullable=True)

    meal_plan = relationship("MealPlan", back_populates="items")
    recipe = relationship("Recipe", back_populates="meal_plan_items")

    __table_args__ = (
        UniqueConstraint("meal_plan_id", "recipe_id", name="uk_plan_recipe"),
    )


class AiConversation(Base):
    """
    AI 对话会话表 —— 每个用户可以有多段独立对话。
    会话标题可由用户设置或由系统从首条消息自动生成。
    """
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="conversations")
    messages = relationship("AiMessage", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_conv_user_id", "user_id"),
    )


class AiMessage(Base):
    """
    AI 消息记录表 —— 每条消息记录角色（user/assistant/system）和内容，
    按 created_at 排序即可还原完整对话时间线。
    tokens 字段用于统计 API 消耗。
    """
    __tablename__ = "ai_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum("user", "assistant", "system"), nullable=False)
    content = Column(Text, nullable=False)
    tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    conversation = relationship("AiConversation", back_populates="messages")

    __table_args__ = (
        Index("idx_conversation_id", "conversation_id"),
    )
"""浏览历史公共工具 —— 单用户单对象去重写入

抽取自 recipes.py 与 users.py 的两份重复实现：
  - recipes.py：菜谱详情页自动记录浏览（仅 recipe_id）
  - users.py：/users/history 接口显式记录（recipe_id / meal_plan_id 二选一）
统一为一份"查已有记录 → 有则更新时间，无则插入"的 upsert 逻辑，
避免两处实现日后各自漂移（如改去重键、改时间源时漏改一边）。

并发安全（多用户/多请求同时访问）：
  应用层"先查后插"在并发下有竞态——同一用户双击卡片时两个请求都查到
  "无记录"而各自插入。数据库层的 (user_id, recipe_id)/(user_id,
  meal_plan_id) 唯一索引兜底拦截重复插入；这里捕获 IntegrityError 并
  回退为更新既有行的时间，保证并发下结果与串行执行一致。
"""

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import UserBrowseHistory


def upsert_browse_history(
    db: Session,
    user_id: int | None,
    recipe_id: int | None = None,
    meal_plan_id: int | None = None,
) -> None:
    """
    记录浏览历史（去重）—— 单用户单对象只保留最近一条记录。

    策略（与原两处实现一致）：
      - user_id 为 None（未登录）：不记录，直接返回
      - 已有该用户对该对象的记录：仅更新 viewed_at，不新增行（避免表膨胀）
      - 无记录：插入新行
    不负责 commit，事务边界由调用方控制。

    并发竞态处理：插入时撞上唯一约束（另一并发请求抢先插入了同一行）
    则回滚本次插入、改走更新分支——等价于"对方先到，我更新时间"。
    """
    if user_id is None:
        return

    query = db.query(UserBrowseHistory).filter(
        UserBrowseHistory.user_id == user_id
    )
    if recipe_id is not None:
        query = query.filter(UserBrowseHistory.recipe_id == recipe_id)
    else:
        query = query.filter(UserBrowseHistory.meal_plan_id == meal_plan_id)

    now = datetime.now()
    existing = query.first()
    if existing:
        existing.viewed_at = now
        return

    db.add(UserBrowseHistory(
        user_id=user_id,
        recipe_id=recipe_id,
        meal_plan_id=meal_plan_id,
        viewed_at=now,
    ))
    try:
        # SAVEPOINT：只回滚这条 INSERT，不影响外层事务中已执行但未提交的
        # 其他变更（如菜谱详情接口的 view_count 原子 UPDATE——它与浏览记录
        # 同事务提交，整段 rollback 会把计数一起冲掉）
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        # 并发请求已抢先插入同一 (user_id, recipe_id/meal_plan_id)：
        # savepoint 已回滚插入，改走更新分支，保持单行语义
        existing = query.first()
        if existing:
            existing.viewed_at = now

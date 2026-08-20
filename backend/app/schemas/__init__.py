"""Pydantic Schema 包 —— 定义所有 API 的请求/响应数据结构

按业务模块拆分：
  - common.py      → 通用结构（分页、错误、成功响应）
  - user.py        → 用户（注册/登录/信息/密码）
  - recipe.py      → 菜谱（CRUD、列表、详情、搜索参数）
  - interaction.py → 互动（点评、心得、套餐）
  - ai.py          → AI（对话请求、推荐请求、会话/消息）
  - admin.py       → 后台管理（审核操作、管理员列表视图）
"""
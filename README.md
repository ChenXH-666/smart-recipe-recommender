# 智能菜谱推荐系统

基于 FastAPI + Vue 3 的智能菜谱推荐平台，集成大语言模型与 RAG 技术，实现个性化菜谱推荐、自然语言搜索、AI 烹饪助手、套餐搭配等功能。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 (Composition API) + Vite + Element Plus |
| 后端 | Python FastAPI + SQLAlchemy + Pydantic |
| 数据库 | MySQL 8.x |
| 向量库 | ChromaDB（本地持久化） |
| 大模型 | LLM 默认小米 Mimo（mimo-v2.5，关闭深度思考）；Embedding/Rerank 恒用 SiliconFlow（BGE-M3 嵌入 + bge-reranker-v2-m3 精排） |
| 认证 | JWT Token |

## 功能模块

### 用户端
| 模块 | 功能 |
|------|------|
| 菜谱服务 | 菜谱浏览、详情查看、关键词/难度/预算筛选、创建/编辑菜谱 |
| 用户中心 | 登录注册、收藏管理、浏览历史、AI对话记录、待做清单（近期要做）、菜谱合集（一键生成套餐） |
| 互动模块 | 菜谱评分点评、烹饪心得分享(创建+浏览) |
| 智能推荐 | 基于用户历史的个性化推荐、预算筛选推荐、自然语言搜索推荐；新号走冷启动多样推荐、忌口过滤前置 |
| AI 助手 | 流式多轮对话、RAG 增强菜谱问答（两阶段检索：BGE-M3 粗排召回 + bge-reranker-v2-m3 交叉编码精排，分数融合 α=0.5 微调排序，精排失败自动降级）、单菜/套餐智能推荐；仅推荐菜谱库内真实菜品，支持用户忌口过滤与预算感知（尽量用足预算） |
| 套餐服务 | 套餐浏览、创建自定义套餐 |

### 管理端
| 模块 | 功能 |
|------|------|
| 仪表盘 | 实时统计数据(菜谱数/待审核/用户数) |
| 菜谱审核 | 待审核菜谱审批(通过/拒绝) |
| 套餐审核 | 待审核套餐审批 |
| 标签管理 | 标签分类 CRUD |
| 食材管理 | 食材增删查 |
| 用户管理 | 用户列表、启用/禁用 |

## 前端页面路由

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | Home | 首页，统计卡片 + 为你推荐/热门菜谱（单行横向滑动）/推荐套餐；AI 对话统一走右下角 AI 助手悬浮入口 |
| `/for-you` | ForYouRecipes | 首页「为你推荐」更多（完整列表） |
| `/hot-recipes` | HotRecipes | 首页「热门菜谱」更多（完整列表） |
| `/recipes` | RecipeList | 菜谱浏览（筛选/搜索，难度支持多选，排序支持字段×方向自由组合） |
| `/recipes/create` | RecipeCreate | 创建菜谱 |
| `/recipes/:id` | RecipeDetail | 菜谱详情 + 评价 |
| `/recipes/:id/edit` | RecipeEdit | 编辑菜谱 |
| `/meal-plans` | MealPlanList | 套餐广场 |
| `/meal-plans/create` | MealPlanCreate | 创建套餐 |
| `/meal-plans/:id` | MealPlanDetail | 套餐详情 |
| `/notes` | CookingNotes | 烹饪心得（浏览+发布） |
| `/login` | Login | 登录 |
| `/register` | Register | 注册 |
| `/user/profile` | Profile | 个人资料 |
| `/user/todo` | TodoList | 待做清单（近期要做） |
| `/user/favorites` | Favorites | 我的收藏 |
| `/user/history` | History | 浏览历史 |
| `/user/conversations` | Conversations | AI 对话历史 |
| `/admin` | AdminDashboard | 管理后台首页 |
| `/admin/recipes` | RecipeAudit | 菜谱审核 |
| `/admin/meal-plans` | MealPlanAudit | 套餐审核 |
| `/admin/tags` | TagManage | 标签管理 |
| `/admin/ingredients` | IngredientManage | 食材管理 |
| `/admin/users` | UserManage | 用户管理 |

## 后端 API 概览

| 前缀 | 说明 |
|------|------|
| `/api/auth` | 认证（登录/注册） |
| `/api/users` | 用户中心（个人信息/收藏/历史/对话） |
| `/api/recipes` | 菜谱 CRUD |
| `/api/reviews` | 菜谱评价 |
| `/api/cooking-notes` | 烹饪心得 |
| `/api/meal-plans` | 套餐 CRUD |
| `/api/ai` | AI 流式对话 |
| `/api/recommendations` | 智能推荐 |
| `/api/stats` | 首页统计（菜谱/套餐/用户总量 + 近7天新增） |
| `/api/admin` | 后台管理 |

## 项目结构

```
Project/
├── backend/
│   ├── app/
│   │   ├── api/           # 接口路由
│   │   ├── core/          # 安全/依赖注入/速率限制
│   │   ├── models/        # SQLAlchemy 模型
│   │   ├── schemas/       # Pydantic 校验
│   │   ├── services/      # 业务逻辑（AI/RAG/推荐）
│   │   ├── config.py      # 配置管理
│   │   ├── database.py    # 数据库连接
│   │   └── main.py        # 应用入口
│   ├── import_data/        # 数据导入脚本（rebuild_vectorstore 向量重建 / eval_rerank 精排论文评测）
│   ├── tests/              # pytest 单元测试
│   ├── .env.example        # 环境变量模板
│   └── requirements.txt    # Python 依赖
├── frontend/
│   ├── src/
│   │   ├── api/           # API 请求封装
│   │   ├── components/    # 通用组件
│   │   ├── layouts/       # 布局
│   │   ├── router/        # 路由
│   │   ├── stores/        # Pinia 状态
│   │   └── views/         # 页面视图
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
└── SQL/
    └── init.sql            # 数据库初始化脚本
```

## 快速开始

### 1. 环境要求
- Python 3.10+
- Node.js 18+
- MySQL 8.x

### 2. 数据库初始化
```bash
# 创建数据库并导入表结构
mysql -u root -p < SQL/init.sql
```

### 3. 后端启动
```bash
cd backend
cp .env.example .env          # 编辑 .env 填入真实 API Key
pip install -r requirements.txt

# 导入基础数据（标签/食材/示例菜谱）
cd import_data
python import_basic_data.py

# 启动服务
uvicorn app.main:app --reload --port 8000
```

### 4. 前端启动
```bash
cd frontend
npm install
npm run dev
```

### 5. 访问
- 前端页面：http://localhost:3000
- API 文档：http://localhost:8000/docs

### 6. 运行单元测试
```bash
cd backend
conda activate food
python -m pytest tests -v --cov=app --cov-report=term-missing
```
单元测试基于 pytest 编写，共 167 个用例，覆盖纯函数 / 模型 / 服务 / 接口四层；测试使用 SQLite 内存库并对 Chroma、LLM 等外部依赖打桩隔离，无需连接真实数据库与模型服务。整体行覆盖率约 59%，核心逻辑（配置、安全、统计、营养、工具函数、AI 引擎）覆盖率 76%~100%。

**存量库升级提示（v1.1 唯一约束）**：浏览历史表新增了防并发重复的数据库唯一约束。新库执行 `SQL/init.sql` 自动生效；**已有旧库**需手动迁移（先清重复行再加约束，SQL 见 `database_design.md` 3.9 节），否则并发双击仍可能产生重复浏览记录。

## 工程优化与性能设计

以下为历次迭代落地的优化项，均为**当前代码已实现**的状态：

### 后端性能

| 优化项 | 位置 | 说明 | 验证方法 |
|--------|------|------|---------|
| AI 对话 RAG 检索线程池化 | `services/ai_service.py` | 检索含同步 Embedding/Rerank HTTP（最长 40s），用 `asyncio.to_thread` 移出事件循环，期间其他接口正常服务 | 发一条 AI 消息的同时刷新其他页面，不应卡顿 |
| SQL 日志独立开关 | `config.py` `SQL_ECHO` | 与 `DEBUG` 解耦，默认关闭，避免演示/压测时日志爆炸 | 默认启动不再打印每条 SQL |
| 首页统计 TTL 缓存 | `api/stats.py` | 7 次聚合 COUNT 缓存 60 秒，首页访问不再全量统计 | 连续两次访问 /api/stats，日志只查一次库 |
| 详情接口 N+1 修复 | `api/recipes.py` | commit 后重新预加载 tags/ingredients/steps/author，避免懒加载回潮 | 打开详情页，后端日志仅 3~4 条 SQL |
| 向量同步后台化 | `services/rag_service.py` `sync_*_by_id` | 创建/编辑/审核菜谱、心得时的 Embedding 同步改 `BackgroundTasks`，不再阻塞响应 | 管理员审核通过菜谱应立即返回，向量同步随后完成 |
| 会话列表摘要查询 | `api/users.py` `get_conversations` | 子查询只取首/末消息 ID + 批量取内容，不再 joinedload 全量消息 | 打开对话历史页，长会话也不慢 |
| LLM 客户端单例 | `services/ai_service.py` `_get_llm` | 复用 `ChatOpenAI`（含 httpx 连接池），避免每轮重建握手 | 连续对话时首轮后无重建开销 |
| 对话历史按需重载 | `api/ai.py` + `has_memory` | 仅内存缓存未命中时才查库重建，活跃会话零 DB 开销 | 连续对话不再每轮全量查历史 |
| 静态封面长缓存 | `main.py` `CachedStaticFiles` | 600+ 封面图 `Cache-Control: max-age=86400` | 刷新两次首页，图片第二次显示 disk/memory cache |
| 菜谱详情/套餐详情浏览记录单写 | 前端删除手动 `recordHistory` | 后端详情接口已自动记录，此前前端双写导致浏览记录翻倍虚高 | 打开详情后浏览历史只新增一条 |

### 前端性能

| 优化项 | 位置 | 说明 | 验证方法 |
|--------|------|------|---------|
| 首页 5 路请求并行 | `views/Home.vue` | 热门/套餐/统计/忌口/推荐并行发起、各自渲染，总耗时=最慢一路 | F12 Network 见 5 个请求同时发出 |
| AI 对话 Markdown 预计算 | `components/AiChatDialog.vue` | 历史消息进列表时渲染一次，流式重渲染不再重复解析 | 长对话流式输出期间页面不卡顿 |
| 封面图懒加载 + 失败兜底 | `components/RecipeCard.vue` | `loading="lazy"` 视口内加载；外链图挂掉回退占位图 | 滚动列表时图片按需加载；断网图片显示占位 |
| 构建分包 | `vite.config.js` | element-plus/图标/markdown 独立 chunk，业务包 1244KB→87KB | `npm run build` 产物多个 vendor chunk |

### 代码质量

| 优化项 | 位置 | 说明 |
|--------|------|------|
| 浏览历史 upsert 公共化 | `utils/browse_history.py` | 详情页与 /users/history 共用一份去重逻辑 |
| 取消收藏公共逻辑 | `api/users.py` | 两个取消收藏接口共用递减+删除逻辑 |
| 前端 API 命名端点统一 | `src/api/index.js` | 27 个文件 88 处字面量调用迁移为命名端点，路径集中管理 |

### 并发安全

| 优化项 | 位置 | 说明 | 验证方法 |
|--------|------|------|---------|
| 浏览历史唯一约束 + IntegrityError 兜底 | `models` / `SQL/init.sql` / `utils/browse_history.py` | 数据库唯一索引兜底并发双插，SAVEPOINT 局部回滚 | 并发双击详情（见下） |
| 收藏并发冲突返回 400 | `api/users.py` | 双击收藏第二个请求返回 400「已收藏」而非 500 | 快速双击收藏按钮 |
| Chroma 单例初始化加锁 | `services/rag_service.py` | 线程池双写初始化竞态防护，热路径不加锁 | 高并发下首次请求不报 Chroma 异常 |

### 并发问题手工复现/验证方法

```bash
# 并发双击浏览历史（无唯一约束的旧库会插入重复行，新库/迁移后被拦截）
# 用两个终端几乎同时请求同一详情：
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/recipes/1" &
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/recipes/1" &
# 然后查浏览历史：新库应只有一行（时间被更新），旧库可能出现两行（需迁移）
```

## 注意事项

- **API Key 配置**：请在 `backend/.env` 中配置真实的 API Key——LLM 用小米 Mimo Key（`LLM_API_KEY`），Embedding/Rerank 用 SiliconFlow Key（`EMBEDDING_API_KEY`，Rerank 自动复用），不要将密钥提交到版本控制
- **向量数据库**：ChromaDB 使用本地持久化，数据库文件保存在 `backend/chroma_db/` 目录
- **默认管理员**：运行导入脚本后自动创建管理员账号 `admin` / `admin123`
- **反向代理部署提醒**：限流按"直连客户端 IP"计数。若把后端部署到 Nginx 等反向代理之后，所有请求的直连 IP 都会变成代理机（如 127.0.0.1），全部访客会共享同一个限流桶（一人触发限流、全体被限）。需给 uvicorn 加 `--proxy-headers --forwarded-allow-ips="代理机IP"`，使其读取 `X-Forwarded-For` 还原真实访客 IP。当前开发环境直连 8000 端口，无此问题
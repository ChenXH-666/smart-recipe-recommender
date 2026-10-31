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
| 混合检索 | 向量（BGE-M3）+ BM25 关键词双路召回，RRF 排名融合（k=60）；BM25 内存索引随向量同步自动失效重建；含预算/人数约束的查询自动跳过关键词通道、退化为纯向量召回 |
| 查询改写 | 无实体词查询（与全库菜名无 ≥3 字连续命中）经 LLM 聚焦补全 1~2 个具体菜名，与原查询双路召回再经 RRF 融合；改写须含库内真实菜名且保留预算约束，否则静默回退原查询；改写文本另以"原查询＋改写文本"拼接形式参与精排打分 |
| 认证 | JWT Token |

## 功能模块

### 用户端
| 模块 | 功能 |
|------|------|
| 菜谱服务 | 菜谱浏览、详情查看、关键词/难度/预算筛选、创建/编辑菜谱 |
| 用户中心 | 登录注册、收藏管理、浏览历史、AI对话记录、待做清单（近期要做）、菜谱合集（一键生成套餐） |
| 互动模块 | 菜谱评分点评、烹饪心得分享(创建+浏览) |
| 智能推荐 | 基于用户历史的个性化推荐、预算筛选推荐、自然语言搜索推荐（用户自写且不含实体词的查询经查询改写补全实体后检索）；新号走冷启动多样推荐、忌口过滤前置 |
| AI 助手 | 流式多轮对话、RAG 增强菜谱问答（查询改写：无实体词需求先经 LLM 聚焦补全 1~2 个菜名再与原查询双路召回 RRF 融合；混合检索：BGE-M3 向量 + BM25 关键词双路召回、RRF 融合，含预算/人数约束的查询退化为纯向量；bge-reranker-v2-m3 交叉编码精排、分数融合 α=0.5 微调排序，改写生效时打分查询取"原查询＋改写文本"，通道/改写失败自动降级）、单菜/套餐智能推荐；仅推荐菜谱库内真实菜品，支持用户忌口过滤与预算感知（尽量用足预算） |
| 套餐服务 | 套餐浏览（广场卡片展示封面图）、创建自定义套餐、用户提交新食材（创建菜谱入口，待管理员审核） |

### 管理端
| 模块 | 功能 |
|------|------|
| 仪表盘 | 实时统计数据(菜谱数/待审核/用户数) |
| 菜谱审核 | 待审核菜谱审批（通过/驳回，驳回必填意见；菜谱详情页亦可直接审核，被驳回菜谱向作者展示驳回原因） |
| 套餐审核 | 待审核套餐审批（通过/驳回，驳回必填意见；套餐详情页亦可直接审核，被驳回套餐向作者展示驳回原因） |
| 标签管理 | 标签分类 CRUD |
| 食材管理 | 食材增删查（含审核状态列） |
| 食材审核 | 审核用户提交的食材（通过/驳回，通过后进入公共食材下拉） |
| 用户管理 | 用户列表、启用/禁用 |

## 前端页面路由

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | Home | 首页，统计卡片 + 为你推荐/热门菜谱（单行横向滑动）/推荐套餐；AI 对话统一走右下角 AI 助手悬浮入口 |
| `/for-you` | ForYouRecipes | 首页「为你推荐」更多（完整列表） |
| `/hot-recipes` | HotRecipes | 首页「热门菜谱」更多（完整列表） |
| `/recipes` | RecipeList | 菜谱浏览（筛选/搜索，难度支持多选，排序支持字段×方向自由组合） |
| `/recipes/create` | RecipeCreate | 创建菜谱（食材清单头部提供「手动添加食材」入口） |
| `/ingredients/create` | IngredientCreate | 创建食材（提交后待管理员审核） |
| `/recipes/:id` | RecipeDetail | 菜谱详情 + 评价（管理员可在详情页直接审核；被驳回菜谱向作者展示驳回原因） |
| `/recipes/:id/edit` | RecipeEdit | 编辑菜谱 |
| `/meal-plans` | MealPlanList | 套餐广场（卡片展示封面图） |
| `/meal-plans/create` | MealPlanCreate | 创建套餐 |
| `/meal-plans/:id` | MealPlanDetail | 套餐详情（管理员可在详情页直接审核；被驳回套餐向作者展示驳回原因） |
| `/cooking-notes` | CookingNotes | 烹饪心得（浏览+发布；旧路径 `/notes` 自动重定向） |
| `/cooking-notes/:id` | CookingNoteDetail | 心得详情 |
| `/login` | Login | 登录 |
| `/register` | Register | 注册 |
| `/user/profile` | Profile | 个人资料 |
| `/user/todo` | TodoList | 待做清单（近期要做） |
| `/user/favorites` | Favorites | 我的收藏 |
| `/user/history` | History | 浏览历史 |
| `/user/conversations` | Conversations | AI 对话历史 |
| `/user/preferences` | Preferences | 饮食偏好设置（忌口/过敏原） |
| `/user/my-recipes` | MyRecipes | 我的菜谱（含草稿/待审核/已驳回） |
| `/user/my-meal-plans` | MyMealPlans | 我的套餐（含草稿/待审核/已驳回） |
| `/admin` | AdminDashboard | 管理后台首页 |
| `/admin/recipe-audit` | RecipeAudit | 菜谱审核（旧路径 `/admin/recipes` 自动重定向） |
| `/admin/meal-plan-audit` | MealPlanAudit | 套餐审核（旧路径 `/admin/meal-plans` 自动重定向） |
| `/admin/tags` | TagManage | 标签管理 |
| `/admin/ingredients` | IngredientManage | 食材管理 |
| `/admin/ingredient-audit` | IngredientAudit | 食材审核（用户提交的食材） |
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
| `/api/admin` | 后台管理（审核/标签/食材/用户管理；`GET /admin/ingredients` 默认仅返回已审核食材供下拉使用，传 `status` 参数仅管理员可用、非管理员返回 403；`POST /admin/ingredients` 允许登录用户提交新食材——管理员直接通过、普通用户进入待审核并记录提交人；`POST /admin/ingredients/{id}/audit` 审核用户提交的食材；`GET /admin/stats` 含 `pending_ingredients` 待审核食材数） |

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
│   ├── import_data/        # 数据导入与评测脚本（rebuild_vectorstore 向量重建 / eval_rerank 检索质量评测 / bench_api 接口性能基准）
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
测试基于 pytest 编写，共 323 个用例，覆盖纯函数 / 模型 / 服务 / 接口四层；数据库使用 SQLite 内存库，LLM/Embedding HTTP 使用假响应，向量写入回归使用关闭遥测的临时内存 Chroma 集合，不访问业务 MySQL、持久化向量目录或模型服务。未安装 pytest-cov 时可运行 `python -m pytest tests -q`。历史行覆盖率约 64%、核心逻辑 77%~100%，本轮未重新测量覆盖率。

### 7. 运行接口性能基准
```bash
cd backend
conda activate food
# 需先注册一个用于压测的普通账号（或用已有账号），凭据通过参数或环境变量 BENCH_USERNAME/BENCH_PASSWORD 传入
python import_data/bench_api.py --username <账号> --password <密码>
python import_data/bench_api.py --username <账号> --password <密码> --skip-ai   # 跳过 AI 首包（省 LLM 额度）
```
以真实 HTTP 请求测量已运行的后端（需后端已运行在 8000 端口，建议以 `--proxy-headers` 启动，否则登录接口"10 次/分钟/IP"的限流会使登录样本自动降为限流窗口内的 10 次）：核心接口串行延迟（N=100）、AI 对话首包延迟（SSE，默认 6 条）、并发承载（10/20/50）与首页统计缓存冷/热对比，结果同时输出 Markdown/JSON 报告（`import_data/bench_api_results.md/.json`，为论文 6.5 节性能测试数据来源）。

### 8. 运行检索质量评测
```bash
cd backend
conda activate food
# 需先停掉后端（避免 Chroma 文件占用），并配置好 Embedding/Rerank/LLM 的 API Key
python import_data/eval_rerank.py --dump-titles                 # 打印库内菜名（评测集标注辅助）
python import_data/eval_rerank.py --out-prefix eval_scenario    # 全模式（7 种召回模式 × α 扫描，为论文 6.4 节数据来源）
python import_data/eval_rerank.py --modes vector,hybrid,hybrid_rw,hybrid_fix,hybrid_rw_fix --out-prefix eval_rewrite
python import_data/eval_rerank.py --diagnose --out-prefix eval_scenario
#                                                                阶段诊断：逐条输出相关菜在通道/单查询RRF/双查询融合/池/精排的名次
# 召回模式：vector=纯向量 / hybrid=混合召回（向量+BM25，RRF）/ hybrid_fix=混合+约束跳过（修复）
#          hybrid_rw=混合+查询改写（双查询 RRF）/ hybrid_rw_fix=混合+查询改写+约束跳过
#          hybrid_rw_fix_rq=精排打分查询取改写文本（消融对照）/ hybrid_rw_fix_rqm=精排打分查询取"原查询＋改写文本"（生产默认全链路）
# 结果同时输出 Markdown/JSON（import_data/eval_*_results.md/.json，为论文 6.4 节实验数据来源）
```
评测集为 `import_data/eval_rerank_cases.json`（20 条分层查询：精确型/类别型/场景意图型/约束型，57 个相关菜谱标注），指标为 Recall@K / MRR / NDCG@K（默认 K=12，与线上候选池上限一致），并附「查询改写记录」（触发与否、改写文本、LLM 耗时）与「池级命中」诊断；`--diagnose` 输出各阶段名次诊断（`eval_*_diagnose.md/.json`），用于定位相关菜在检索链路的哪一步丢失。

**存量库升级提示（v1.1 唯一约束）**：浏览历史表新增了防并发重复的数据库唯一约束。新库执行 `SQL/init.sql` 自动生效；**已有旧库**需手动迁移（先清重复行再加约束，SQL 见 `database_design.md` 3.9 节），否则并发双击仍可能产生重复浏览记录。

**存量库升级提示（点评唯一约束）**：点评表新增 `UNIQUE(user_id, recipe_id)`（`uk_review_user_recipe`），防止并发重复点评，并配合"软删除后重新点评复用原行"的实现。新库执行 `SQL/init.sql` 自动生效；**已有旧库**需先清理同一用户同一菜谱的重复点评再加约束（优先保留未删除行，SQL 见 `database_design.md` 10 节），否则并发重复提交仍可能产生多条记录。

**存量库升级提示（食材审核字段）**：食材表新增 `status`/`submitted_by` 两列（用户可提交新食材、管理员审核）。新库执行 `SQL/init.sql` 自动生效；**已有旧库**需手动迁移：`ALTER TABLE ingredients ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'approved'; ALTER TABLE ingredients ADD COLUMN submitted_by INT UNSIGNED NULL;` 执行后历史食材自动置为 `approved`，如需归入官方账号可执行 `UPDATE ingredients SET submitted_by=1;`（1 为默认官方管理员「官方小厨」的 ID，按实际账号调整）。

## 工程优化与性能设计

以下为历次迭代落地的优化项，均为**当前代码已实现**的状态：

### 后端性能

| 优化项 | 位置 | 说明 | 验证方法 |
|--------|------|------|---------|
| AI 对话 RAG 检索线程池化 | `services/ai_service.py` | 检索含同步 Embedding/Rerank HTTP（最长 40s），用 `asyncio.to_thread` 移出事件循环，期间其他接口正常服务 | 发一条 AI 消息的同时刷新其他页面，不应卡顿 |
| SQL 日志独立开关 | `config.py` `SQL_ECHO` | 与 `DEBUG` 解耦，默认关闭，避免演示/压测时日志爆炸 | 默认启动不再打印每条 SQL |
| 首页统计 TTL 缓存 | `api/stats.py` | 7 次聚合 COUNT 缓存 60 秒，首页访问不再全量统计 | 连续两次访问 /api/stats，日志只查一次库 |
| 详情接口 N+1 修复 | `api/recipes.py` | commit 后重新预加载 tags/ingredients/steps/author，避免懒加载回潮 | 打开详情页，后端日志仅 3~4 条 SQL |
| 标签筛选子查询去重 | `api/recipes.py` | `tag_ids` 筛选改用 `IN` 子查询替代 JOIN：一个菜谱命中多个标签时 JOIN 会产生重复行，导致 `total` 计数虚高、分页结果重复 | 同时选多个标签筛选，总数与结果不重复 |
| 审核列表 reviewer 预加载 | `api/admin.py` | 菜谱/套餐审核列表补 `joinedload(reviewer)`，消除循环内逐行懒加载 | 打开后台审核列表，SQL 条数不随行数增长 |
| 套餐个性化推荐 items 预加载 | `services/recommendation_service.py` | 命中数排序需遍历套餐菜品，补 `selectinload(items)`（集合关系用 selectinload 避免 JOIN 行膨胀） | 登录用户查看推荐套餐，SQL 条数固定 |
| 收藏状态单条查询 | `api/users.py` `GET /users/favorites/check` | 详情页判断是否已收藏，替代"拉全量 50 条收藏列表遍历比对" | 打开详情页，Network 中是一次 check 请求 |
| 向量同步后台化 | `services/rag_service.py` `sync_*_by_id` | 创建/编辑/审核菜谱、心得时的 Embedding 同步改 `BackgroundTasks`，不再阻塞响应 | 管理员审核通过菜谱应立即返回，向量同步随后完成 |
| 查询改写按需触发 | `services/rag_service.py` `plan_query_rewrite` | 仅当查询与全库菜名无 3 字以上连续命中（如"快手家常菜"）时才调用一次 LLM 改写，已含实体词的查询零开销；提示词聚焦 1~2 个菜名（并列菜名过多会分散检索权重）；改写结果校验不过（幻觉菜名/丢预算）即回退原查询 | 发"清蒸鲈鱼的做法"无改写日志、发"减脂晚餐"有"查询改写生效"日志；改写链路失败时对话仍正常返回 |
| 约束类查询跳过关键词通道 | `services/rag_service.py` `query_has_explicit_constraint` | 含预算/人数约束的查询（如"预算100元的东北菜家常菜""三个人吃的晚餐"）跳过 BM25 关键词通道、退化为纯向量召回——"东北""家常"等泛类别词的字面命中会挤占语义命中的位次（回退与修复效果见 `PRD.md` 5.4 节评测）；仅约束类查询受影响 | 发"预算100元的东北菜"有"约束类查询跳过关键词通道"日志；跑评测 `--modes vector,hybrid,hybrid_fix` 约束组指标回到向量基线 |
| 精排打分查询融合改写文本 | `services/rag_service.py` `_effective_rerank_query` | 改写生效时精排打分查询取"原查询＋改写文本"拼接（未触发/回退仍用原查询）：口语化原查询会让交叉编码对相关菜给低分、压出前 12（诊断见论文 6.4.5 节②），拼接则同时保留菜名与类别词信号；不新增外部调用与延迟（前后指标见 `PRD.md` 5.4 节评测） | 发"下班后30分钟搞定的快手家常菜"，日志显示精排生效；跑评测 `--modes hybrid_rw_fix,hybrid_rw_fix_rq,hybrid_rw_fix_rqm` 对比三档精排查询取法 |
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
| AI 消息稳定 key + 滚动节流 | `components/AiChatDialog.vue` | v-for key 由 index 改为消息唯一标识（编辑重答截断数组后 DOM 不再错乱）；流式滚动 150ms 节流，避免微任务堆积 | 编辑中间消息重答，气泡/编辑态不错位 |
| 套餐菜谱搜索防抖 | `views/MealPlanCreate.vue` | `remote-method` 300ms 防抖，键入停顿后才发请求，组件卸载清理定时器 | 连续输入时 Network 只发一次搜索请求 |
| 详情页相关心得 | `views/RecipeDetail.vue` | 侧边栏按 `recipe_id` 加载关联心得（原为声明后从未加载的死代码），无数据时卡片自动隐藏 | 打开有心得的菜谱详情，右侧显示相关心得 |
| 封面图懒加载 + 失败兜底 | `components/RecipeCard.vue` | `loading="lazy"` 视口内加载；外链图挂掉回退占位图 | 滚动列表时图片按需加载；断网图片显示占位 |
| 构建分包 | `vite.config.js` | element-plus/图标/markdown 独立 chunk，业务包 1244KB→87KB | `npm run build` 产物多个 vendor chunk |

### 代码质量

| 优化项 | 位置 | 说明 |
|--------|------|------|
| 浏览历史 upsert 公共化 | `utils/browse_history.py` | 菜谱/套餐详情页与 /users/history 共用一份去重 + 并发兜底逻辑 |
| 取消收藏公共逻辑 | `api/users.py` | 两个取消收藏接口共用递减+删除逻辑 |
| 前端 API 命名端点统一 | `src/api/index.js` | 27 个文件 88 处字面量调用迁移为命名端点，路径集中管理 |
| 会话 updated_at 显式刷新 | `api/ai.py` | 插入/删除消息不会触发会话行 `onupdate`，三处消息变更点显式赋值，会话列表"按最新排序"真正生效 |
| LLM 失败轮次不落库 | `api/ai.py` + `services/ai_service.py` | 失败提示（`AI_ERROR_MSG`）不写消息表也不进对话记忆；流中途失败时剥掉错误尾缀、仅把已流出的真实正文落库并保留进上下文 |
| Embedding 查询侧失败降级修复 | `services/rag_service.py` `embed_query` | 查询嵌入失败由零向量兜底改为抛异常——零向量在 L2 距离下仍能返回任意结果，"退化为关键词匹配"实际不触发（约束类纯向量链路全量失真）；抛异常后由各通道异常处理正确降级 |
| RAG 召回最外层兜底 | `services/rag_service.py` `build_recipe_pool_context` | `get_vectorstore()` 初始化失败等穿透 rag_search 内部降级的异常，吞掉后走热门兜底，对话退化为热门推荐而非整轮报错 |
| 限流器失活 key 清扫 | `core/rate_limit.py` | 每 1000 次检查全量清理 1 小时失活的 IP 桶，避免 `_store` 长期膨胀 |
| 资料更新走 store action | `stores/user.js` `updateUserInfo` | Profile 页不再直接改写 `userStore.user`，统一经 action 同步 store 与 localStorage |
| 存在性预言机封堵 | `api/reviews.py` + `api/users.py` | 点评列表对非公开菜谱一律 404（此前遍历 id 可由 200/404 差异枚举未过审菜谱并读到其点评）；手动记录浏览历史接口与收藏口径对齐，仅接受 approved 目标 |
| 密码强度策略注册/改密共用 | `core/security.py` | `validate_password_strength` 统一校验"≥8 位且含字母与数字"，修改密码不再绕过注册时的强度规则 |
| 点评软删除后重新点评复用原行 | `api/reviews.py` | 每人每菜谱仅一行；删除后再次点评恢复原行并刷新评分/内容/时间，避免唯一约束阻止重建 |
| 心得关联菜谱可见性 | `api/cooking_notes.py` | 仅 approved 且未删除的菜谱可被关联；菜谱后续被驳回或软删除时不再回显标题，避免公开心得泄露未公开内容 |
| 匿名智能搜索限流与入参上限 | `api/recommendations.py` + `schemas/ai.py` | `/query` 匿名可用但按 IP 限流 20 次/分钟；query 1~200 字符、budget 非负，避免匿名刷取 Embedding/精排额度 |
| 403 不再误清登录态 | `src/api/index.js` | 后端统一异常把 `detail` 置空并放入 `message`；403 仅提示无权限，只有 401（令牌缺失/失效）才清除本地登录态并跳转登录 |

### 并发安全

| 优化项 | 位置 | 说明 | 验证方法 |
|--------|------|------|---------|
| 浏览历史唯一约束 + IntegrityError 兜底 | `models` / `SQL/init.sql` / `utils/browse_history.py` | 数据库唯一索引兜底并发双插，SAVEPOINT 局部回滚 | 并发双击详情（见下） |
| 收藏并发冲突返回 400 | `api/users.py` | 双击收藏第二个请求返回 400「已收藏」而非 500 | 快速双击收藏按钮 |
| 点评唯一约束 + IntegrityError 兜底 | `models` / `SQL/init.sql` / `api/reviews.py` | 数据库唯一索引兜底并发重复提交，冲突返回 400「已点评过」；软删除后重新点评复用原行 | 并发提交同一菜谱点评，仅保留一条 |
| 注册/标签/食材先查后插兜底 | `api/auth.py` / `api/admin.py` | 预检通过后的并发写由 username/email、标签 `(name,type)`、食材 name 唯一约束拦截，捕获 `IntegrityError` 后回查冲突字段并返回 400；标签 type 为 NULL 时 MySQL 唯一索引不参与判断，无数据库兜底（现有表结构限制） | 并发注册同名账号、创建同名食材或同 name+type 标签，后者收到 400 |
| 邮箱修改竞态兜底 | `api/users.py` `update_profile` | 先查后改存在竞态，并发撞 unique 约束时捕获 `IntegrityError` 返回 400 而非 500 | 两请求同时改同一邮箱，后者收到 400 |
| 统计缓存防击穿 | `api/stats.py` | 缓存过期瞬间多请求并发时，双重检查锁保证只有一路回源（7 次聚合 COUNT） | 缓存过期瞬间并发请求，日志仅一次统计查询 |
| Chroma 单例初始化加锁 | `services/rag_service.py` | 线程池双写初始化竞态防护，热路径不加锁 | 高并发下首次请求不报 Chroma 异常 |
| 向量写入串行锁 | `services/rag_service.py` `_vs_write_lock` | 同进程同步、删除与重建串行执行，防止 upsert 与过期分块清理交错；后台同步执行时复查 approved/is_public 状态。锁不跨进程，独立重建脚本须在停止其他索引写入后执行 | 用临时内存 Chroma 验证更新、删除与重建结果 |

### 并发问题手工复现/验证方法

```bash
# 并发双击浏览历史（无唯一约束的旧库会插入重复行，新库/迁移后被拦截）
# 用两个终端几乎同时请求同一详情：
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/recipes/1" &
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/recipes/1" &
# 然后查浏览历史：新库应只有一行（时间被更新），旧库可能出现两行（需迁移）
```

## RAG / SSE 可靠性修复记录（2026-10-28）

| 问题 | 修复与验证 |
|------|------------|
| Chroma 复合删除条件被拒绝却记录成功 | 使用 `$and` 组合来源类型与 ID；删除失败向上传播，清除 BM25 缓存；使用真实内存 Chroma 验证只删除目标来源 |
| Embedding 索引错位、异常响应通过校验 | 严格校验数量、整数索引唯一且连续（排除 bool）、非空向量、维度和有限数值；拒绝零向量。BGE-M3 校验 1024 维，其他配置模型校验本次调用内维度一致 |
| 嵌入失败补零、先删除导致有效索引丢失 | 文档和查询嵌入失败均抛错；查询仍可走关键词/热门兜底。增量同步先嵌入并 upsert，成功后才删除多余旧块；失败不主动删除原分块 |
| 全量重建先清库、失败后只剩半库 | 不再启动即清库；按批 upsert，成功后原子替换断点文件，所有批次完成才清理过期 ID；失败保留未完成批次旧数据和已保存断点，清理失败也可续传 |
| SSE 提前报告结束、保存失败不可见 | `[DONE]` 在保存处理完成后发送；保存失败返回不含内部异常的提示并清除会话内存，避免与数据库历史不一致 |

验证：`cd backend` 后运行 `python -m pytest tests -q --disable-warnings`，本轮 **323 passed，23 warnings**；无 xfail。覆盖异常索引/向量、增量写入失败不删旧块、重建中断与恢复、断点替换失败、SSE 结束标记当下的数据持久化、保存失败与会话权限。警告来自已有依赖弃用及 SciPy/NumPy 版本兼容提示，未修改环境或升级依赖。

边界与运维：
- 本轮未连接生产服务，也未重建现有持久化索引；历史零向量和旧分块不会因为改代码自动消失，需另行安排重建。
- 全量重建是逐批更新，不是全库原子切换；失败时已完成批次保留新版本，其他批次保留旧版本。失败任务续传期间须保持源数据、分块配置和 Embedding 模型不变；源数据或分块配置变更后应使用 `--from-scratch` 重新计算。更换 Embedding 模型须另建兼容集合并完整重建，不能靠断点续传混用向量空间，本次未实现模型迁移工具。
- `--from-scratch` 现在表示忽略断点并重新编码全部可见内容，成功后清理旧数据，而非开头清空集合。独立脚本或多进程部署必须停止其他索引写入后再重建；进程内锁不能替代跨进程协调。
- 新内容的嵌入失败后暂时没有新向量，更新失败则保留旧索引；系统未新增自动重试队列，需要重试同步或重建。已经发生存储局部写入时，不承诺跨操作事务回滚。
- SSE 客户端中途断开、进程崩溃时的回答持久化仍不是可靠投递保证；本次保证的是正常流结束前完成保存处理。
- 已更正此前生命周期判断：本机 FastAPI 0.136.3 的默认 yield 依赖在流结束后关闭，不属于“流开始前 Session 已关闭”的缺陷。

## 注意事项

- **API Key 配置**：请在 `backend/.env` 中配置真实的 API Key——LLM 用小米 Mimo Key（`LLM_API_KEY`），Embedding/Rerank 用 SiliconFlow Key（`EMBEDDING_API_KEY`，Rerank 自动复用），不要将密钥提交到版本控制
- **向量数据库**：ChromaDB 使用本地持久化，默认目录由 `CHROMA_PERSIST_DIR` 配置（默认 `F:/chroma_db`，纯 ASCII 绝对路径，避免 Windows 中文路径导致 HNSW 索引加载失败）；重建断点文件 `rebuild_checkpoint.json` 也保存在该目录下
- **默认管理员**：运行导入脚本后自动创建管理员账号 `admin` / `admin123`
- **反向代理部署提醒**：限流按"直连客户端 IP"计数。若把后端部署到 Nginx 等反向代理之后，所有请求的直连 IP 都会变成代理机（如 127.0.0.1），全部访客会共享同一个限流桶（一人触发限流、全体被限）。需给 uvicorn 加 `--proxy-headers --forwarded-allow-ips="代理机IP"`，使其读取 `X-Forwarded-For` 还原真实访客 IP。当前开发环境直连 8000 端口，无此问题
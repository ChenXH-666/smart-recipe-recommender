# 智能菜谱推荐系统

基于 FastAPI + Vue 3 的智能菜谱推荐平台，集成大语言模型与 RAG 技术，提供菜谱浏览与创作、自然语言搜索、AI 烹饪助手、个性化推荐、套餐搭配与内容审核等功能。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3（Composition API）+ Vite + Element Plus |
| 后端 | Python FastAPI + SQLAlchemy + Pydantic |
| 数据库 | MySQL 8.x |
| 向量库 | ChromaDB（本地持久化） |
| 大模型 | 小米 Mimo mimo-v2.6-flash（OpenAI 兼容接口） |
| 嵌入与精排 | SiliconFlow：BAAI/bge-m3 嵌入 + bge-reranker-v2-m3 精排 |
| 检索 | 向量召回 + BM25 关键词召回，RRF 排名融合；无实体词查询按需改写 |
| 认证 | JWT + bcrypt |

## 功能模块

### 用户端

| 模块 | 功能 |
|------|------|
| 菜谱服务 | 浏览、详情、关键词/难度/预算筛选与排序、创建/编辑菜谱、营养估算、忌口提示 |
| 用户中心 | 登录注册、个人资料、收藏、浏览历史、AI 对话记录、待做清单、菜谱合集 |
| 互动分享 | 菜谱点评、烹饪心得发布与浏览、套餐创建与收藏 |
| 智能推荐 | 个性化推荐、预算推荐、自然语言搜索推荐、冷启动多样推荐 |
| AI 助手 | 多轮流式对话、RAG 菜谱问答、食材替代建议、预算内菜单搭配 |
| 套餐服务 | 套餐广场、套餐详情、自定义套餐、用户提交新食材 |

### 管理端

| 模块 | 功能 |
|------|------|
| 仪表盘 | 菜谱/用户/套餐/待审核数量统计 |
| 内容审核 | 菜谱、套餐、用户提交食材的通过/驳回 |
| 基础数据 | 标签管理、食材管理、用户启用/禁用与角色调整 |

## 页面路由

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | 首页 | 统计卡片、为你推荐、热门菜谱、推荐套餐 |
| `/for-you`、`/hot-recipes` | 为你推荐/热门菜谱 | 首页「查看更多」的完整列表 |
| `/recipes` | 菜谱列表 | 多维筛选、排序、智能搜索 |
| `/recipes/:id` | 菜谱详情 | 食材、步骤、营养、点评、收藏 |
| `/recipes/create`、`/recipes/:id/edit` | 创建/编辑菜谱 | 需登录 |
| `/meal-plans`、`/meal-plans/:id` | 套餐广场/详情 | 公开套餐浏览 |
| `/meal-plans/create` | 创建套餐 | 需登录 |
| `/cooking-notes`、`/cooking-notes/:id` | 烹饪心得列表/详情 | 支持 Markdown |
| `/ingredients/create` | 提交新食材 | 需登录，管理员审核后生效 |
| `/login`、`/register` | 登录/注册 | 独立页面 |
| `/user/*` | 个人中心 | 资料、收藏、历史、对话、偏好、我的菜谱/套餐、待做清单 |
| `/admin/*` | 管理后台 | 仪表盘、内容审核、用户/标签/食材管理 |

## 后端 API 概览

| 前缀 | 说明 |
|------|------|
| `/api/auth` | 注册、登录、当前用户 |
| `/api/recipes` | 菜谱 CRUD、热门菜谱 |
| `/api/reviews` | 菜谱点评 |
| `/api/cooking-notes` | 烹饪心得与评论 |
| `/api/meal-plans` | 套餐 CRUD、购物清单 |
| `/api/users` | 用户中心、收藏、浏览历史、AI 对话记录 |
| `/api/ai` | AI 流式对话（SSE）、会话管理 |
| `/api/recommendations` | 个性化推荐、预算推荐、自然语言搜索 |
| `/api/stats` | 首页统计 |
| `/api/admin` | 后台管理、内容审核、基础数据维护 |
| `/api/health` | 健康检查（数据库连通性） |

## 项目结构

```
Project/
├── backend/
│   ├── app/
│   │   ├── api/           # 接口路由
│   │   ├── core/          # 安全、依赖注入、限流
│   │   ├── models/        # SQLAlchemy 模型
│   │   ├── schemas/       # Pydantic 校验
│   │   ├── services/      # AI / RAG / 推荐服务
│   │   ├── utils/         # 通用工具
│   │   ├── config.py      # 配置管理
│   │   ├── database.py    # 数据库连接
│   │   └── main.py        # 应用入口
│   ├── import_data/       # 数据导入与向量库重建脚本
│   ├── static/            # 菜谱封面等静态资源
│   ├── tests/             # pytest 测试
│   ├── .env.example       # 环境变量模板
│   ├── IMPORT_GUIDE.md    # 数据导入与部署说明
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/           # 请求封装
│   │   ├── components/    # 通用组件
│   │   ├── layouts/       # 布局
│   │   ├── router/        # 路由
│   │   ├── stores/        # Pinia 状态
│   │   ├── utils/         # 工具（SSE、Markdown 等）
│   │   └── views/         # 页面
│   ├── vite.config.js
│   └── package.json
├── SQL/
│   └── init.sql            # 数据库初始化脚本
├── PRD.md                  # 产品需求文档
├── database_design.md      # 数据库设计
└── README.md
```

## 快速开始

### 1. 环境要求

- Python 3.10+、Node.js 18+、MySQL 8.x

### 2. 初始化数据库

```bash
mysql -u root -p < SQL/init.sql
```

### 3. 启动后端

```bash
cd backend
cp .env.example .env          # 填入数据库与 API Key
pip install -r requirements.txt

cd import_data
python import_basic_data.py   # 导入基础数据

cd ..
uvicorn app.main:app --reload --port 8000
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

### 5. 访问

- 前端：http://localhost:3000
- API 文档：http://localhost:8000/docs
- 后台管理：默认管理员 `admin` / `admin123`（首次导入数据后创建）

### 6. 运行测试

```bash
cd backend
python -m pytest tests -q
```

## 配置说明

- **API Key**：在 `backend/.env` 中配置 `LLM_API_KEY`（小米 Mimo）与 `EMBEDDING_API_KEY`（SiliconFlow，Rerank 自动复用）；敏感配置不要提交到版本控制。
- **向量库**：ChromaDB 本地持久化，目录由 `CHROMA_PERSIST_DIR` 配置，需为不含中文的绝对路径。
- **数据导入**：菜谱、套餐、封面与向量库重建步骤见 `backend/IMPORT_GUIDE.md`。
- **反向代理**：若部署在 Nginx 等代理之后，需给 uvicorn 加 `--proxy-headers --forwarded-allow-ips="代理机IP"`，使限流按真实访客 IP 计数。
- **存量库升级**：历史数据库的表结构迁移 SQL 见 `database_design.md`。

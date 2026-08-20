# 智能菜谱推荐系统

基于 FastAPI + Vue 3 的智能菜谱推荐平台，集成大语言模型与 RAG 技术，实现个性化菜谱推荐、自然语言搜索、AI 烹饪助手、套餐搭配等功能。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 (Composition API) + Vite + Element Plus |
| 后端 | Python FastAPI + SQLAlchemy + Pydantic |
| 数据库 | MySQL 8.x |
| 向量库 | ChromaDB（本地持久化） |
| 大模型 | SiliconFlow API (DeepSeek-R1 + BGE-M3) |
| 认证 | JWT Token |

## 功能模块

### 用户端
| 模块 | 功能 |
|------|------|
| 菜谱服务 | 菜谱浏览、详情查看、关键词/难度/预算筛选、创建/编辑菜谱 |
| 用户中心 | 登录注册、收藏管理、浏览历史、AI对话记录 |
| 互动模块 | 菜谱评分点评、烹饪心得分享(创建+浏览) |
| 智能推荐 | 基于用户历史的个性化推荐、预算筛选推荐、自然语言搜索推荐 |
| AI 助手 | 流式多轮对话、RAG 增强菜谱问答、单菜/套餐智能推荐 |
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
| `/` | Home | 首页，热门推荐 + AI 智能搜索 |
| `/recipes` | RecipeList | 菜谱浏览（筛选/搜索） |
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
│   ├── import_data/        # 数据导入脚本
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

## 注意事项

- **API Key 配置**：请在 `backend/.env` 中配置真实的 SiliconFlow API Key，不要将密钥提交到版本控制
- **向量数据库**：ChromaDB 使用本地持久化，数据库文件保存在 `backend/chroma_db/` 目录
- **默认管理员**：运行导入脚本后自动创建管理员账号 `admin` / `admin123`
# 菜谱数据导入指南

`backend/import_data/` 下的脚本用于初始化系统数据。均在 `backend` 目录下执行。

## 前置条件
1. 数据库已通过 `SQL/init.sql` 初始化
2. 已配置 `.env`（参考 `.env.example`）
3. 已安装依赖：`pip install -r requirements.txt`

## 导入步骤

### 1. 导入基础数据（必须）
```bash
python import_data/import_basic_data.py
```
创建系统初始账号与基础维度数据：
- 官方账号 `admin / admin123`（官方小厨，管理员）、`tester`（内测达人）等
- 标签（菜系/菜品类型/烹饪方式/场景/膳食/季节）
- 食材

### 2. 导入菜谱
```bash
python import_data/import_recipes.py
```
从 `data/useful/` 目录读取菜谱数据（标题、描述、食材、步骤、标签等），自动去重标签与食材，自动创建不存在的作者用户。

### 3. 导入套餐（可选）
```bash
python import_data/import_meal_plans.py
```
导入预置套餐数据。

### 4. 生成菜谱封面图（可选）
```bash
python import_data/generate_covers.py
```
为菜谱生成本地文字封面图（菜名 + 渐变背景），URL 写入数据库。不依赖网络。

### 5. 重建向量库（RAG 需要）
```bash
python import_data/rebuild_vectorstore.py
```
将已审核通过的菜谱与公开心得写入 Chroma 向量库，供 RAG 语义检索使用。支持断点续传。

## 验证
- 后端启动后访问 `http://localhost:8000/docs` 查看 API
- 用 `admin / admin123` 登录管理后台

## 说明
- 脚本均自动处理重复数据（标签/食材按名称去重），可安全重复执行
- 向量库路径 `CHROMA_PERSIST_DIR` 必须是不含中文的绝对路径（ChromaDB 限制）

# Pagefolio

本地年度阅读书目管理 — Browser / Server 架构，数据存 SQLite，封面存本地。

## 架构

```
Browser (web/)          Server (pagefolio/)           Data
─────────────          ───────────────────           ─────
index.html      ←→    Flask REST API          ←→    reading.db
  │                    pagefolio/server/             cover/
  └─ assets/           pagefolio/db.py
                       pagefolio/sources/     ← 豆瓣 / Amazon / Goodreads
                       pagefolio/covers.py    ← 批量刮封面 (CLI)
```

| 层 | 目录 | 职责 |
|----|------|------|
| **Browser** | `web/` | 静态页面：`index.html`、占位图等 |
| **Server** | `pagefolio/server/` | Flask 服务：页面 + `/api/*` |
| **Domain** | `pagefolio/db.py` | 数据库 schema、迁移、序列化 |
| **Sources** | `pagefolio/sources/` | 外站元数据解析（手动匹配用） |
| **Covers** | `pagefolio/covers.py` | 批量封面刮削（CLI） |
| **Data** | `reading.db`, `cover/` | 用户本地数据（不入库 git） |
| **Agent** | `SKILL.md` | Cursor Agent 操作说明 |

## 快速开始

```bash
python3 -m pip install -r requirements.txt
python run.py init      # 初始化 reading.db
python run.py           # 启动 → http://127.0.0.1:8765
```

其他命令：

```bash
python run.py scrape              # 批量刮封面
python run.py scrape --year 2025  # 仅某年
```

兼容旧路径：`scripts/init_db.py`、`scripts/server.py`、`scripts/scrape_covers.py` 仍可用。

## API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/years` | 有阅读记录的年份列表 |
| GET | `/api/reading?year=` | 按年、按月书目 |
| GET | `/api/books/:id` | 书目详情 |
| POST | `/api/books/:id/verify-source` | 验证外站链接并预览 |
| POST | `/api/books/:id/match-source` | 确认更新书目与封面 |

Agent 录入书目、批量导入等流程见根目录 [SKILL.md](SKILL.md)。

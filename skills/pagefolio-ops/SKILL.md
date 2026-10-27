---
name: pagefolio-ops
description: Pagefolio 服务运维技能：重启后端、更新豆瓣 Cookie、健康检查与 403 排查。当用户说「重启后台/后端」「更新 cookie」「豆瓣 403」「服务挂了」时使用。
---

# Pagefolio 运维技能

## 项目坐标

| 项 | 值 |
|---|---|
| 项目根 | `/Users/fuyu/Project2025/pagefolio` |
| 服务地址 | `http://127.0.0.1:8765` |
| 启动入口 | `python3 run.py serve` |
| 管理脚本 | `./serve.sh {restart\|start\|stop\|status\|logs}` |
| PID 文件 | `.pagefolio.pid` |
| 日志 | `/tmp/pagefolio_serve.log` |
| 健康检查 | `GET /api/years` 返回 200 |
| Cookie 配置 | `pagefolio/config.py` 的 `DOUBAN_COOKIE` |

## 一、重启后端

### 标准方式

```bash
cd /Users/fuyu/Project2025/pagefolio && ./serve.sh restart
```

脚本会：按 PID 文件停旧进程 → 清理占用 8765 端口的残留进程 → `nohup` 启动 → 等端口 LISTEN → 校验 `/api/years` 返回 200。

### 沙箱环境下的可靠方式（优先）

在 Agent 沙箱中，普通 Shell 命令退出时可能连带回收 `nohup` 子进程。改用后台任务模式：

```bash
cd /Users/fuyu/Project2025/pagefolio && rm -f .pagefolio.pid && python3 run.py serve
```

以 `run_in_background: true` 执行，随后验证：

```bash
sleep 3 && curl -s -o /dev/null -w "HTTP %{http_code}" http://127.0.0.1:8765/api/years && echo "" && lsof -nP -iTCP:8765 -sTCP:LISTEN -t
```

期望：`HTTP 200` + 一个 PID。

### 重启判定标准（不要只看进程存在）

1. `lsof -nP -iTCP:8765 -sTCP:LISTEN -t` 有输出
2. `curl /api/years` 返回 `HTTP 200`
3. 启动失败时读 `/tmp/pagefolio_serve.log` 尾部 15 行定位

### 何时需要重启

- 改 `pagefolio/` 下任何 `.py`（后端）→ **需要重启**
- 改 `web/` 下 `.html/.css/.js`（静态文件）→ **不需要重启**，刷新浏览器即可
- 改 `pagefolio/config.py`（含 Cookie）→ **需要重启**

## 二、更新豆瓣 Cookie

豆瓣对未登录/失效 Cookie 返回 **HTTP 403**（响应体通常不足 1KB 的反爬页）。有效登录 Cookie 的特征是同时包含 `dbcl2` 与 `ck` 字段，且 `dbcl2` 形如 `"用户ID:随机串"`。

### 步骤

1. 用户从浏览器（已登录 book.douban.com）F12 → Network → 任意 `book.douban.com` 请求 → Headers → 复制整行 `Cookie:` 值。
2. 替换 `pagefolio/config.py` 中 `DOUBAN_COOKIE` 的**三引号字符串**（`"""..."""` 内部）。若 `PAGEFOLIO_DOUBAN_COOKIE` 环境变量已设置，会优先使用环境变量，此时需提示用户。
3. 重启后端（见上）。
4. 验证 Cookie 有效：

```bash
cd /Users/fuyu/Project2025/pagefolio && python3 -c "
from pagefolio.sources.douban import session
from bs4 import BeautifulSoup
resp = session.get('https://book.douban.com/subject/1007305/', timeout=(8, 30))
print(f'status: {resp.status_code}, length: {len(resp.text)}')
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'lxml')
    h1 = soup.select_one('h1 span[property=\"v:itemreviewed\"]')
    print('title:', h1.get_text(strip=True) if h1 else '未找到标题')
"
```

通过标准：`status: 200` + 能解析出书名（如《红楼梦》）。若为 403，说明 Cookie 无效或已过期，需用户重新获取。

### 注意

- 只替换三引号内的值，保留 `os.environ.get(...)` 的优先级逻辑。
- 不要在回复中完整回显 Cookie（含登录凭证）；只说明已写入及关键字段是否齐全。
- Cookie 会随豆瓣风控失效，403 是常态而非代码 Bug，优先引导用户换 Cookie。

## 三、常见故障

| 现象 | 排查 |
|---|---|
| 端口已监听但健康检查非 200 | `tail -30 /tmp/pagefolio_serve.log` 看异常栈 |
| 启动即退出 | 直接前台跑 `python3 run.py serve` 看报错 |
| 端口被占用 | `lsof -nP -iTCP:8765 -sTCP:LISTEN`，`./serve.sh restart` 会兜底清理 |
| 豆瓣 403 | Cookie 失效 → 走「二、更新豆瓣 Cookie」 |
| 静态页面改动不生效 | 无需重启，硬刷新浏览器（Cmd+Shift+R） |

## 四、约定

- 服务只监听 `127.0.0.1:8765`，不要擅自改端口/绑定地址。
- 重启后用 `/api/years` 做健康检查，不要仅凭「进程存在」判定成功。
- 数据文件 `reading.db`、封面目录 `cover/` 不要随重启清理。

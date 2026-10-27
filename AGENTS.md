# Pagefolio · 会话常驻上下文

本文件在每次会话开始时加载。详细操作步骤见 [skills/pagefolio-ops/SKILL.md](skills/pagefolio-ops/SKILL.md)。

## 服务

- 项目根：`/Users/fuyu/Project2025/pagefolio`
- 服务：`http://127.0.0.1:8765`，入口 `python3 run.py serve`，管理脚本 `./serve.sh`
- 日志：`/tmp/pagefolio_serve.log`；PID：`.pagefolio.pid`
- 健康检查：`GET /api/years` → 200

## 重启后台

标准：`./serve.sh restart`

Agent 沙箱内（避免 nohup 子进程被回收）：以后台任务执行
`rm -f .pagefolio.pid && python3 run.py serve`，
然后用 `curl -s -o /dev/null -w "HTTP %{http_code}" http://127.0.0.1:8765/api/years` 验证 200。

**只有改 `pagefolio/*.py` 或 `pagefolio/config.py` 才需要重启；改 `web/` 静态文件刷新浏览器即可。**

## 豆瓣 Cookie

- 位置：`pagefolio/douban_cookie.txt`（单行原始 Cookie，已被 `.gitignore` 忽略）；`PAGEFOLIO_DOUBAN_COOKIE` 环境变量优先级更高
- 读取逻辑：`pagefolio/config.py` 的 `DOUBAN_COOKIE = _load_douban_cookie()`
- 有效特征：包含 `dbcl2`（形如 `"用户ID:随机串"`）与 `ck`
- 失效表现：`HTTP 403`，响应体 < 1KB 的反爬页
- 更新后必须重启，并用 `https://book.douban.com/subject/1007305/` 验证：状态 200 且能解析出书名
- 回复中不要完整回显 Cookie 值

## 其它约定

- 服务只监听 `127.0.0.1:8765`，不改端口/绑定地址
- 重启成功判定：端口 LISTEN + 健康检查 200，不能只看进程存在
- 不要清理 `reading.db` 与 `cover/`

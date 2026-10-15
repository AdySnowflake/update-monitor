## 项目管理

- 本项目使用 uv 管理 Python、虚拟环境和依赖
- 添加依赖：使用 `uv add <package>`
- 安装锁定依赖：使用 `uv sync --locked`
- 运行项目：使用 `uv run --locked python main.py`
- 配置环境：`cp .env.example .env`，然后填入 API Key

## 服务器部署

- 使用非交互式 SSH 执行部署命令时，先在目标服务器确认 `uv` 的绝对路径。通过远端 `command -v uv` 查找；远端 `PATH` 尚未包含 `uv` 时，检查远端用户的 `$HOME/.local/bin/uv`，并执行该文件的 `--version` 验证可用性。
- 远程安装依赖和运行项目时，先进入服务器上的项目根目录，再使用已确认的 `uv` 绝对路径执行 `sync --locked` 或 `run --locked python main.py`。
- 配置 cron 时，显式设置包含 `uv` 安装目录的 `PATH`，或在任务命令中使用 `uv` 的绝对路径。
- 配置定时任务前，先创建项目的 `logs/` 目录，确保 cron 的日志重定向可以正常打开目标文件。
- cron 运行项目时使用 `flock -n /tmp/update-monitor.lock`，让上一轮仍在运行时跳过新一轮，避免重复下载、重复待办和并发写入规则文件。部署验证期间手动运行 `main.py` 时使用同一把锁。

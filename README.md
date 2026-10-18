# Update Monitor

Update Monitor 包含两条独立业务线：

- **GitHub Release**：检查最新 Release，使用 OpenAI 兼容模型筛选 asset，下载、按需移动文件，并创建 TickTick 待办。
- **App Store**：通过 Apple 查询接口获取版本，与记录比较，变化时使用规则中的名称通过飞书或 TickTick 推送。

两条业务线各自维护规则文件，共用通知入口。每轮先执行两条业务线的完整检查，再补跑失败的仓库或应用一次，随后汇总仍然失败的错误、尝试生成 AI 错误报告，并通过飞书自定义机器人发送通知。

程序每次执行一轮检查，每轮包含首遍执行和一次失败项补跑，适合由 cron 或其他任务调度器定时运行。

## GitHub Release 处理流程

```text
读取 repo_rules.json
        │
        ▼
逐个查询 GitHub 最新 Release（单仓库失败不阻断其他仓库）
        │
        ├─ tag 与 last_tag 相同 ──────────────► 跳过
        │
        ├─ tag 未包含 tag_contains 关键词 ────► 跳过（配置时生效）
        │
        ▼
主 LLM 一次处理全部筛选组，每组选一个 asset（失败时重试）
        │
        ├─ 主 LLM 最终失败 ─► 备用 LLM（可选，同样重试）
        │
        ▼
校验每组均有下载地址，且全部来自 Release assets
        │
        ▼
依次下载到 downloads/ 下的仓库与 Tag 专属缓存目录
        │
        ▼
整组转移到目标目录（可选，支持部分成功后重试）
        │
        ▼
创建 TickTick 待办（可选、非阻断）
        │
        ▼
整组成功后更新 last_tag
```

每轮在两条业务线首遍执行完毕后收尾：

```text
仅补跑首遍失败的仓库和应用一次
        │
        ▼
移除已恢复项，按最终结果累计 GitHub 失败轮数
        │
        ▼
汇总仍需告警的检查、处理和版本通知投递失败
        │
        ▼
尝试让主/备用 LLM 生成错误报告
        │
        ├─ 分析成功 ─► 可读报错 + AI 分析 ─► 飞书告警
        │
        └─ 分析失败 ─► 可读报错，无 AI 内容 ─► 飞书告警
```

补跑会重新执行失败监控项的查询与处理流程，已成功项保留首遍结果。规则文件整体读取失败时，补跑对应业务线。GitHub 的失败计数和自动禁用在补跑结束后处理，同一仓库每轮最多累计一次失败。

AI 错误分析与飞书发送是两条解耦的路径。即使 LLM 因 API Key 余额耗尽、鉴权失败或服务不可用而无法分析，程序仍会直接发送原始错误通知。文件选择阶段已经确认不可用的模型不会被错误分析再次调用。

## 环境要求

- Python 3.12（项目要求 `>=3.12,<3.13`）
- [uv](https://docs.astral.sh/uv/)
- GitHub Release 文件选择需要一个 OpenAI 兼容的聊天模型接口；版本监控直接使用来源接口
- 可选：GitHub Token、TickTick、飞书自定义机器人

## 快速开始

```bash
git clone <repository-url> update-monitor
cd update-monitor

cp .env.example .env

# 按需启用业务线，可以只复制其中一个规则文件
cp repo_rules.example.json repo_rules.json
cp apple_rules.example.json apple_rules.json

# 编辑 .env 和对应的规则文件后安装并运行
uv sync --locked
uv run --locked python main.py
```

运行日志会写入 `logs/pipeline_YYYYMMDD_HHMMSS.log`，下载文件按仓库和 Tag 的 SHA-256 摘要分目录保存在 `downloads/`，同一 Release 重试时复用完整文件。

入口只运行已有规则文件对应的业务线。两条业务线各自隔离异常，某条业务线失败后继续执行另一条。

## 更新已有部署

项目通过 Git 部署后，进入项目目录拉取最新代码并同步依赖：

```bash
cd /path/to/update-monitor
git pull --ff-only
uv sync --locked
```

程序每次由 cron 启动并执行一轮检查，不需要重启常驻服务。下一轮任务会自动使用更新后的代码。

## 配置 LLM

主模型用于选择 Release asset，也是错误分析的首选模型：

```dotenv
LLM_PRIMARY_BASE_URL=https://api.example.com/v1
LLM_PRIMARY_API_KEY=sk-your-key
LLM_PRIMARY_MODEL=your-model
# 单次请求超时，默认 30 秒
LLM_REQUEST_TIMEOUT_SECONDS=30
```

使用 GitHub Release 文件选择时，`LLM_PRIMARY_API_KEY` 与 `LLM_PRIMARY_MODEL` 必填。使用服务商默认地址时可以省略 `LLM_PRIMARY_BASE_URL`。只使用版本监控时可以省略 LLM 配置；出现错误时仍会尝试 AI 分析，配置缺失则直接发送原始错误告警。

备用模型可选。建议使用不同的 API Key 或服务商，使主接口发生配额、网络或服务故障时仍有回退能力：

```dotenv
LLM_FALLBACK_BASE_URL=https://api.example.com/v1
LLM_FALLBACK_API_KEY=sk-your-fallback-key
LLM_FALLBACK_MODEL=your-fallback-model
```

备用模型只有同时填写 API Key 和模型名时才启用；配置不完整时按未启用处理。

文件选择时，每个模型默认调用 3 次：首次调用加 2 次指数退避重试。OpenAI 客户端自身的重试已关闭，主模型全部失败后才会切换备用模型。最终失败时记录最后一次异常。

所有环境变量只由 `config.py` 读取。`clients/llm.py` 仅负责按角色惰性创建和缓存客户端，不包含用户专属 Provider 配置。

## 配置 GitHub Release 监控规则

监控清单位于 `repo_rules.json`，可复制 [repo_rules.example.json](repo_rules.example.json) 后修改。示例使用标准 JSON，字段的可选性和省略行为见下表。

```json
{
  "owner/repo-name": {
    "filters": [
      {
        "extension": ".apk",
        "include": ["arm64-v8a"],
        "exclude": ["legacy"]
      },
      {
        "extension": ".apk",
        "include": ["armeabi-v7a"],
        "exclude": ["legacy"]
      }
    ],
    "tag_contains": "phone",
    "last_tag": null,
    "disabled": false
  }
}
```

仓库键 `owner/repo-name` 必填，格式为 `owner/repo`。`filters` 必填，至少包含一个筛选组；每组选择一个文件，单文件下载填写一组即可。仓库层的其余字段可选。

| 字段 | 类型 | 是否必填 | 说明与省略行为 |
| --- | --- | --- | --- |
| `filters` | object[] | 必填 | 非空筛选组数组，组内字段见下表；一次 LLM 请求按顺序为全部组各选一个文件 |
| `tag_contains` | string/null | 可选 | Tag 按大小写精确匹配子串；省略、`null` 或 `""` 表示接受任意 Tag |
| `last_tag` | string/null | 可选，程序维护 | 最后成功处理的 tag；省略或 `null` 时首次处理当前最新 Release，成功后自动更新 |
| `disabled` | boolean | 可选 | 省略时启用；`true` 时跳过该仓库，连续失败 3 轮后程序也会设为 `true` |
| `consecutive_failures` | number | 可选，程序维护 | 省略时从 0 开始累计；成功或自动禁用后移除，示例中省略此字段 |

每个筛选组的字段均可选：

| 字段 | 类型 | 说明与省略行为 |
| --- | --- | --- |
| `extension` | string | 文件扩展名，例如 `.apk`、`.exe`；省略时没有扩展名限制 |
| `include` | string[] | 文件名应同时包含的全部关键词；省略或 `[]` 时没有包含关键词要求 |
| `exclude` | string[] | 文件名应排除的全部关键词；省略或 `[]` 时没有排除关键词要求 |

每组独立筛选，`filters: [{}]` 表示从 assets 中选一个最合适的文件。任意一组未选出文件，则该仓库本轮处理失败；多组选择相同的 URL 时合并下载一次。只有 `filters` 会传给 LLM，`tag_contains` 继续由程序在检查 Release 时处理。

已有部署升级时，将仓库顶层的 `extension`、`include`、`exclude` 移入 `filters` 的第一个对象，保留 `tag_contains`、`last_tag`、`disabled` 和失败计数。旧的平铺筛选字段需要在部署新代码前迁移。新增筛选组后仍沿用 Tag 去重；需要重新处理当前 Release 时，将 `last_tag` 设为 `null`。

程序比较的是 GitHub “latest release”的 tag 与 `last_tag` 是否相同，不进行语义化版本排序。首次运行时 `last_tag` 可设为 `null`，此时会处理当前最新 Release。

例如，设置 `"tag_contains": "phone"` 后，`v1.2.3-phone` 会进入后续文件选择和下载流程，`v1.2.3-TV` 会被跳过。Tag 筛选仅作用于 GitHub 返回的 latest Release；历史 Release 搜索属于独立功能，当前流程仅判断本次返回的版本。筛选跳过视为正常检查完成，保留 `last_tag` 并清除已有失败状态。`tag_contains` 的类型非法时，按该仓库检查失败累计次数，并执行下述告警和自动禁用规则。

`repo_rules.json` 缺失时跳过 GitHub Release 业务线；JSON 无效时按业务线整体失败补跑一次。单仓库字段取值非法（如 `disabled` 不是布尔值）作为该仓库失败处理，其他仓库继续执行；补跑后仍失败的项按下述规则累计并告警。空对象 `{}` 表示暂时没有需要监控的仓库。

需要排序并统一格式化两份规则文件时运行：

```bash
uv run --locked python sort_repo_rules.py
```

该脚本同时整理 `repo_rules.json` 和 `apple_rules.json`：GitHub 按仓库名（`/` 后面的部分）排序，App Store 按顶层监控项名称排序，均忽略字母大小写。两份文件统一使用 UTF-8、两空格缩进、冒号后一个空格和文件末尾单个换行，中文直接保留。条目已经有序时也会修正格式，排序和格式均规范时跳过写入。保留每项字段及其值，尚未创建的规则文件自动跳过。

### 失败重试与自动禁用

每轮首遍检查结束后，GitHub 检查失败和 Release 处理失败的仓库各补跑一次。补跑仍失败时累计连续失败轮数；补跑成功时清除失败状态。跨轮检查间隔由 cron 控制：

| 情形 | 行为 |
| --- | --- |
| `disabled` 为 `true` | 跳过该仓库 |
| 第 1 轮失败 | 保存 `consecutive_failures: 1`，进入本轮汇总告警 |
| 第 2 轮失败 | 保存 `consecutive_failures: 2`，只记录本地日志 |
| 第 3 轮失败 | 移除计数并写入 `disabled: true`，在汇总告警中包含错误原因及恢复方法 |
| 检查成功且无新 Release，或 Tag 被筛选跳过 | 清除连续失败计数 |
| Release 处理成功 | 更新 `last_tag`，清除连续失败计数 |

每段连续故障最多尝试 3 轮，每轮最多执行两遍、累计一次失败，发送 2 次故障通知。第三轮的禁用说明与错误合并进同一条汇总告警，自动禁用记录直接使用原始错误，省去重复的 AI 分析。LLM 每次执行的短暂重试和备用模型回退保持原有配置。规则文件整体读取失败等业务线级错误补跑一次后，仍然失败则进入本轮汇总告警。

例如 cron 每 30 分钟执行一次，首次失败后约 30 分钟重试，约 60 分钟时第三次失败并自动禁用；实际执行时间取决于 cron 调度和每轮耗时。

修复问题后，将 `disabled` 改为 `false` 或删除该字段即可恢复监控。失败期间保留 `last_tag`，恢复后继续处理待完成的 Release。旧版 `next_check_after` 字段已停止参与调度，后续记录失败或清除失败状态时自动移除。

## 配置 App Store 监控

App Store 使用独立的 `apple_rules.json`，可复制 [apple_rules.example.json](apple_rules.example.json) 后修改。示例使用标准 JSON，字段的可选性和默认值见下表。

```json
{
  "SenPlayer": {
    "app_id": "6443975850",
    "notify": ["feishu", "ticktick"],
    "country": "us",
    "version": "6.2.3",
    "disabled": false
  }
}
```

外层名称由用户自定义，例如 `SenPlayer`、`我的播放器`；它用于标识监控项，同时作为通知中的应用名称，查询时使用 `app_id`。

监控项名称（如 `SenPlayer`）、`app_id` 和 `notify` 必填，其余字段均可选。示例将必填字段放在前面，可选字段放在后面。

| 字段 | 类型 | 是否必填 | 说明与省略行为 |
| --- | --- | --- | --- |
| `app_id` | string/number | 必填 | Apple 应用 ID，支持正整数或数字字符串 |
| `notify` | string[] | 必填 | 明确指定至少一个通知渠道；支持 `feishu`、`ticktick`，可选择一个或同时选择 |
| `country` | string | 可选 | App Store 两位地区代码，省略时为 `"us"`；`"cn"` 表示中国区 |
| `version` | string/null | 可选，程序维护 | 已通知的版本；省略或 `null` 时首次推送当前版本，全部渠道送达后自动更新 |
| `disabled` | boolean | 可选 | 省略时为 `false`；`true` 时跳过该项的查询、通知和版本更新 |

填入上述 `version: "6.2.3"` 后，查询仍为 `6.2.3` 时跳过；查询变为其他版本时，通知标题为 `应用名称 - 版本号`，正文为 `Update Monitor - App Store` 和 App Store 链接。规则中填写的版本作为你的监控起点，示例值仅供参考。

所选渠道需要在 `.env` 中启用并填写凭据：飞书使用 `FEISHU_ENABLED=true`，TickTick 使用 `TODO_ENABLED=true`。更新通过飞书蓝色卡片或 TickTick 当天的全天待办送达。

全部所选渠道成功后，程序只更新该项的 `version`。部分或全部渠道失败时保留原版本，本轮补跑及后续轮次会再次向所选渠道发送；已成功的渠道在这种情况下也会再次收到通知。JSON 始终保持上述配置结构。

单个应用的配置、查询或通知失败后继续检查其他项。两条业务线首遍执行结束后，仅补跑失败项；补跑仍然失败的记录进入本轮汇总告警。`apple_rules.json` 缺失时跳过 App Store 业务线，空对象表示当前没有监控项。暂停某个应用时设置 `"disabled": true`，恢复时改为 `false` 或删除该字段。App Store 的该开关用于手动暂停，失败重试继续沿用原有流程。

## 公共版本处理与通知接口

`clients/app_store.py` 专门处理 Apple 查询接口，将规则中传入的监控项名称与查询得到的 `version`、`trackViewUrl` 整理为 `VersionInfo(name, version, url)`。`workflows/apple.py` 负责读取 App Store 清单、传入监控项名称、调用查询以及保存版本。

拿到版本信息之后，通过 `workflows/versions.py` 的 `process_version(info, previous_version, channels)` 统一比较版本和通知。比较采用字符串是否相同的判断。以后接入其他业务线时，各自负责获取信息和维护配置，再将名称、版本和链接交给这个公共函数。

`notifications/` 提供 `Notification(title, content, level)` 和 `send_notification(message, channels)`。业务线组织通知内容、指定渠道，公共入口负责独立投递并返回各渠道的成功状态。`level` 用于选择飞书卡片颜色：更新为蓝色，错误为红色。TickTick 接收相同消息的标题和正文。

GitHub Release 的待办和汇总错误告警均使用这个通知入口，自动禁用说明合并在汇总告警中。GitHub 的待办失败继续按原有的非阻断策略处理；App Store 以全部所选渠道送达作为完成条件。

新增通知渠道时，实现接收 `Notification`、返回布尔值的发送函数，并加入 `NOTIFIERS` 注册表。业务线可以直接在渠道列表中使用注册名称。

## 配置飞书通知

在飞书群中添加启用“签名校验”的自定义机器人，然后将 Webhook 和签名密钥写入当前项目的 `.env`：

```dotenv
FEISHU_ENABLED=true
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
FEISHU_SIGNING_SECRET=your-signing-secret
```

飞书通知由 `notifications/feishu.py` 使用项目已有的 `requests` 依赖实现，消息类型为交互式卡片。版本更新使用蓝色卡片，以下错误通知使用红色卡片。

告警使用红色卡片，标题固定为 `Update Monitor 告警`，每轮运行只汇总发送一条：

- 发生时间；
- 故障仓库和 tag，或版本监控项标识；
- 以代码文本框显示由失败发生处传递的最终错误日志；
- AI 给出的分析内容（仅分析成功时）。

告警不在通知层翻译错误码或生成错误描述，不定义程序中不存在的严重级别或运行状态，也不会展示重试次数、内部错误码或 JSON。错误记录会提供给 AI 分析，本地日志保留完整异常。

GitHub 仓库仅在首次失败和第三轮失败触发自动禁用时进入汇总告警；禁用说明随该仓库的错误一起展示，包含暂停原因和手动恢复方法。第二轮失败只记录本地日志。

以下情况不会阻止错误通知：

- 主模型无法生成错误分析；
- 主、备用模型均无法生成错误分析；
- 没有配置备用模型。

只有 `FEISHU_ENABLED=true` 时才启用飞书通知，此时 Webhook 和签名密钥必须同时填写。未启用时不会额外调用 LLM 生成错误报告。Webhook 无效或通知请求失败时，程序会记录错误，但无法再通过飞书报告自身的发送故障。

## 其他可选配置

### GitHub Token

```dotenv
GITHUB_TOKEN=github_pat_your-token
```

未配置时使用 GitHub 匿名 API；配置后使用认证请求，可降低匿名接口速率限制的影响。

### HTTP 代理

```dotenv
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

代理用于 GitHub API、Apple 查询接口、文件下载、TickTick 和飞书 Webhook 请求。

### TickTick 待办

```dotenv
TODO_ENABLED=true
TICKTICK_ACCESS_TOKEN=your-access-token
TICKTICK_PROJECT_ID=your-project-id
```

启用后，GitHub Release 在全部文件下载及可选转移成功后创建一个上海时区当天的全天待办。单文件与多文件使用相同格式：标题为 `仓库名 - tag`，正文为 `GitHub release monitor`。TickTick 创建失败只记录日志，Release 继续按下载和移动结果更新 `last_tag`；该类非阻断失败沿用原有处理方式。App Store 通过规则中的 `notify` 选择此渠道，失败时保留原版本供下一轮重试。

### 移动下载文件

```dotenv
MOVE_TARGET_DIR=/path/to/target
```

配置后，整组文件下载完成再转移到目标目录，目标目录不存在时自动创建。整组转移采用先复制、全部完成后删除源文件的方式；复制阶段失败时保留下载缓存，下一轮复用完整下载和内容相同的已转移文件。内容不同的同名目标文件会报错并保留原文件。本轮失败时保留 `last_tag`，下轮按同一组规则重试。

## GitHub Release 成功与失败判定

只有以下步骤都成功时才更新对应仓库的 `last_tag`：

1. 获取到 Release assets；
2. LLM 为每个筛选组各选出一个文件；
3. 每个 URL 均属于当前 Release，数量与筛选组数量一致；
4. 去重后的全部文件下载成功；
5. 配置了文件移动时，整组转移成功。

TickTick 是非阻断功能，不参与成功判定。飞书错误通知也不改变 Release 的处理结果。

一轮中某个仓库失败不会阻止其他仓库继续处理。GitHub 403、网络失败、无效响应及后续处理错误都会汇总进入错误分析和通知流程；仓库确实没有 Release 的 404 响应仍视为正常跳过。

## 定时运行

先手动运行一次，确认环境配置、目录权限和日志均正常。然后使用 `crontab -e` 添加任务，例如每 30 分钟执行一次：

```cron
PATH=/home/your-user/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

*/30 * * * * cd /path/to/update-monitor && flock -n /tmp/update-monitor.lock uv run --locked python main.py >> /path/to/update-monitor/logs/cron.log 2>&1
```

通过 SSH 部署时，远程命令的 `uv` 路径确认、cron 环境和运行锁要求见 [AGENTS.md 的服务器部署说明](AGENTS.md#服务器部署)。

## 项目结构

```text
main.py                   # 日志初始化、业务线调度和汇总告警
config.py                 # 环境变量与项目根目录
models.py                 # ReleaseInfo、VersionInfo 数据结构
clients/                  # 外部服务查询与客户端
├── github.py             # GitHub Release 查询与 Tag 条件匹配
├── app_store.py          # Apple 应用版本和链接查询
└── llm.py                # 主/备用 LLM 客户端
notifications/            # 公共通知接口
├── dispatcher.py         # 消息结构、渠道注册与独立投递
├── feishu.py             # 飞书卡片、签名和发送
├── ticktick.py           # TickTick 待办创建
└── alerts.py             # 汇总错误与自动禁用告警内容
workflows/                # 业务流程
├── github.py             # GitHub 仓库轮询与 Release 处理
├── github_rules.py       # 仓库规则、版本记录、失败计数和禁用状态
├── release.py            # asset 筛选、下载、移动与成功通知
├── apple.py              # App Store 清单、查询编排与版本保存
└── versions.py           # 获取版本后的公共比较与更新通知
ai/                       # 模型处理逻辑
├── file_selector.py      # asset 筛选、重试和模型回退
└── error_analysis.py     # 汇总错误分析
files/                    # 文件操作
├── download.py           # 流式下载与临时文件处理
└── transfer.py           # 文件移动
sort_repo_rules.py        # 同时排序并格式化 GitHub 和 App Store 规则
.env.example              # 环境变量模板
repo_rules.example.json   # GitHub Release 规则模板
apple_rules.example.json  # App Store 规则模板
tests/                    # 核心业务流程测试
```

业务线调用 `clients/` 获取信息，使用 `ai/` 和 `files/` 完成处理，再通过 `notifications/` 发送消息。通知渠道的 HTTP 请求与签名逻辑直接归入各自渠道模块，方便一起维护。

`repo_rules.json`、`apple_rules.json`、`.env`、`logs/` 和 `downloads/` 继续位于项目根目录；文件迁移后通过 `config.BASE_DIR` 保持目录定位。运行命令和 cron 配置沿用原有方式。

## 测试

```bash
uv run --locked python -m unittest discover -s tests -v
```

保留 4 个核心业务测试：GitHub 连续失败时的告警与自动禁用，以及 App Store 的版本保存与去重、投递失败后重试和禁用跳过。外部查询和通知使用 mock，规则文件在临时目录中实际读写。

## 安全说明

- `.env`、`repo_rules.json`、`apple_rules.json`、`downloads/` 和 `logs/` 已加入 `.gitignore`。
- 不要把 LLM API Key、GitHub Token、TickTick Token、飞书 Webhook 或签名密钥提交到版本库。
- 错误分析可能会把第三方 API 异常消息发送给已配置的 LLM；飞书通知会包含最终错误摘要和可选的 AI 分析，请选择合适的模型服务与飞书群。

## 许可证

[MIT License](LICENSE)

# 架构

```
┌────────────┐   HTTP/1.1 (loopback)   ┌────────────┐   WBIPC 命名管道   ┌──────────────┐
│ OpenCode   │ ──────────────────────► │ bridge.py  │ ────────────────► │ WorkBuddy    │
│ Codex CLI  │  /v1/chat/completions   │            │  wb.request       │ 桌面端       │
│ Cursor     │  /v1/responses          │            │  http.fetch       │ (登录态/鉴权)│
│ openai-sdk │  /v1/models  /health    └─────┬──────┘                   └──────┬───────┘
└────────────┘                               │                                 │ HTTPS
                                             │ 读产品配置                       ▼
                              ~/.workbuddy/cache/               WorkBuddy 网关
                              acc-product-config-v3.json        /v2/chat/completions
                                                                （扣积分）
```

## 多实例：一个进程一个积分池

```
instances.json
├─ cn     port 18490  config_dir D:\wbt\.workbuddy            provider workbuddy
└─ intl   port 18491  config_dir C:\Users\<you>\.workbuddy-ai  provider workbuddy-intl
        ↓
bridge.py --instance cn      ← 一个 Python 进程
bridge.py --instance intl    ← 另一个 Python 进程
```

为什么不做「一个端口多账号调度」：

- 扣费来源必须能一眼看出来。混在一个端口里，日志里 `model=glm-5.3` 无法回答
  「这句话花的是哪份订阅」。
- 两个版本各自有独立的登录态和产品配置。共享进程意味着共享
  `WORKBUDDY_CONFIG_DIR` 这个全局状态，一处漂移就串账。
- 隔离还带来运维收益：一个版本挂了、一个版本被厂商改管道，另一个照常跑。

### 隔离靠什么保证

| 机制                                  | 位置                                | 作用                                                         |
| ------------------------------------- | ----------------------------------- | ------------------------------------------------------------ |
| `WORKBUDDY_CONFIG_DIR` 显式即唯一来源 | `bridge.py::_config_dir_candidates` | 自动探测只在该变量为空时生效，杜绝「挑最新目录」串到另一版本 |
| `--instance` 在 import 之前改环境     | `instance.py::apply`                | 其余模块读到的环境变量已经是本实例的                         |
| 端口决定日志与快照目录                | `bridge.py` 的 `_SUFFIX`            | `bridge-18491.log` / `dumps-18491/`，排查时不会拿错文件      |
| 产品配置按配置目录读                  | `bridge.py::PRODUCT_CONFIG`         | 模型清单、倍率、`reasoning_effort` 全部来自本版本的配置      |

## 层次

### 1. 上行层：WBIPC

WorkBuddy 桌面端在登录后开一条命名管道，并写一份 `wbipc/endpoint.json`（端点 + 票据）。
它随安装包分发一个纯标准库的 Python 客户端 `workbuddy_ipc`，WorkBuddy 自己的 skills 就走这条路。

```python
from workbuddy_ipc import connect
client = connect(client_id="...", client_kind="skill", client_version="1.0.0")
pipe   = client.get_pipe("wb.request")
resp   = pipe.invoke("http.fetch", {"method": "POST", "path": "/v2/chat/completions",
                                    "headers": {...}, "body_b64": "..."}, timeout=600)
```

三条关键约束：

- **import 而不是 vendoring**。`wbpaths.py` 找到安装目录，把
  `resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/library`
  加进 `sys.path`。复制进仓库既侵权，也会和用户装的版本对不上。
- **握手失败即「未登录」**。`endpoint.json` 是陈旧的——桌面端关掉后文件还在。
  所以 `doctor.py` 和 `setup.py` 都**真开一次管道**，而不是检查文件存不存在。
- **帧体积有上限**。响应体超过桌面端硬编码阈值会 `E_PAYLOAD_TOO_LARGE`（见 `LIMITATIONS.md`）。

### 2. 协议层：`bridge.py`

标准库 `ThreadingHTTPServer`，四条路由：

| 路由                        | 用途                                                                              |
| --------------------------- | --------------------------------------------------------------------------------- |
| `GET /health`               | `{status, label, instance, port, wbipc:{available,info}, models, product_config}` |
| `GET /v1/models`            | 桌面端选单的投影，名字带倍率（`GLM-5.3 (0.79x)`）                                 |
| `POST /v1/chat/completions` | Chat Completions，SSE 或合并                                                      |
| `POST /v1/responses`        | Responses API，由 `responses_api.py` 翻译                                         |

请求流水线：

```
body → 白名单字段过滤(ALLOWED) → reasoning_effort 校正 → 上游调用
     → [relay-models.json 命中? → relay_chat : upstream_chat]
     → 逐帧解析(data: ...) → stream ? SSE 回放 : aggregate 合并
```

**字段白名单**是刻意的：客户端（OpenCode / Codex / AI SDK）会带 `user`、`metadata`、
`stream_options` 之类上游不认识的字段，原样透传就 400。白名单之外一律丢弃。

**上游永远 `stream: true`**，因为网关拒绝非流式；桥接自己在本地聚合，
所以「非流式响应」是桥接合成的，不是上游给的。

**重试只有一次，且只对非常规 `E_UPSTREAM`**。超时不重试——上游可能还在跑，
重试会重复扣费。

### 3. 翻译层：`responses_api.py`

Codex 从 0.4x 起只说 Responses API，并硬性拒绝 `wire_api = "chat"`。这里做双向映射：

| 方向 | 内容                                                                                                                                                                                                              |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 请求 | `instructions`→system message、`input[]`→`messages[]`、`tools`(Responses)→`tools`(Chat)、`reasoning.effort`→`reasoning_effort`                                                                                    |
| 响应 | Chat SSE 分片 → 标准事件序列：`response.created` → `in_progress` → `output_item.added` → `content_part.added` / `reasoning_summary_part.added` → `*.delta` → `*.done` → `output_item.done` → `response.completed` |

usage 字段同时写 `prompt_tokens`/`completion_tokens` 和 `input_tokens`/`output_tokens`，
因为不同版本的 Codex 读不同的键。

## 模型清单的唯一来源

不维护 `models.json`。每次启动读桌面端的
`cache/acc-product-config-v3.json`，取 `agents[name=cli].models` 作为选单，
用 `models[].credits`（形如 `"x0.11"`）生成倍率后缀，用
`supportsToolCall` / `supportsImages` / `maxInputTokens` 生成能力与上下文上限。

代价：桌面端没装/没跑时清单为空。
收益：永远不会推荐一个已经下架的模型，也永远不会报错的价格。

## 部署形态

`setup.py` 是唯一的入口，它把上面这些拼起来：

```
发现安装 → 逐个真开管道 → 排除不可达会话 → 分配端口 → 写 instances.json
        → 每实例起一个进程并等 /health → 合并客户端配置（备份+校验）
        → 注册登录自启 + 10 分钟保活
```

目标是一个**刚从 GitHub clone 下来、机器上装好 WorkBuddy 并登录了**的人，
跑一条 `python setup.py` 就能用；失败时每一步都给出可执行的下一步，而不是堆栈。

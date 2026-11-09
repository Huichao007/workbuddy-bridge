# 客户端接入细节

通用前提：桥接在跑（`python doctor.py` 全 PASS），基址 `http://127.0.0.1:18490/v1`
（第二个实例是 18491，以此类推），API key 填任意非空字符串（桥接不校验）。

`python setup.py` 已经把这些都写好了。这一页是参考：它到底写了什么、怎么手动改、
以及各客户端自己的坑。

---

## 一个实例一份 provider

`setup.py` 给每个活着的积分池建一个 provider，id 规则固定：

| 版本           | provider id                      | 端口     |
| -------------- | -------------------------------- | -------- |
| 国内版         | `workbuddy`                      | 18490    |
| 国际版         | `workbuddy-intl`                 | 18491    |
| 同版本装了多个 | `workbuddy2` / `workbuddy-intl2` | 依次往后 |

`GET /health` 和 `GET /v1/models` 都是**按实例分别回答**的，所以
`http://127.0.0.1:18491/health` 的 `label` 会告诉你它服务的是哪一个版本 ——
分不清钱从哪扣的时候，先看这个。

---

## OpenCode

OpenCode v2 的 provider 声明：

```json
{
  "providers": {
    "workbuddy": {
      "name": "WorkBuddy 国内版 (China)",
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": { "baseURL": "http://127.0.0.1:18490/v1" },
      "models": { "...": "从 /v1/models 现读" }
    }
  }
}
```

v1 把 `settings.baseURL` 换成 `options.baseURL`，其余相同。

`models` 留空也能用（OpenCode 会拉 `/v1/models`），但填上能拿到倍率后缀和正确的
context 上限。`setup.py` 会填，并且：

- **只动 `providers.<id>`**，别的 provider 和顶层键原样保留；
- 写前备份成 `opencode.json.bak-setup-<时间戳>`；
- 写完重新读一遍，校验 `baseURL` 落到了预期端口；
- 你手动改过的模型显示名和额外字段会保留，只覆盖桥接给的事实（baseURL 和模型集合）。

单独同步（不跑整套 setup）：

```powershell
python tools\sync-opencode.py --provider workbuddy --port 18490 --apply
python tools\sync-opencode.py --provider workbuddy-intl --port 18491 --apply
```

**为什么需要同步脚本**：WorkBuddy 的模型清单是服务端下发的，你本地缓存的那份迟早过期，
过期后选择器会给你一个网关直接 400 的 id。脚本以桥接为唯一真源，永远对齐。

调用：

```powershell
opencode run -m workbuddy/glm-5.3 "重构这个函数"
opencode run -m workbuddy-intl/glm-5.3 "用国际版额度问同一个问题"
```

## Codex CLI

`setup.py` 往 `%CODEX_HOME%\config.toml`（默认 `~\.codex\config.toml`）追加：

```toml
[model_providers.workbuddy]
name = "WorkBuddy 国内版 (China)"
base_url = "http://127.0.0.1:18490/v1"
wire_api = "responses"
env_key = "WORKBUDDY_API_KEY"

[model_providers.workbuddy-intl]
name = "WorkBuddy International (国际版)"
base_url = "http://127.0.0.1:18491/v1"
wire_api = "responses"
env_key = "WORKBUDDY_API_KEY"
```

```powershell
$env:WORKBUDDY_API_KEY = "wb-bridge-local"
codex -c model_provider=workbuddy -c model=glm-5.3 exec "..."
```

要点：

- `wire_api` 必须是 `responses`。Codex 新版本会直接拒绝 `chat` 并给出迁移提示。
- `env_key` 必须指向一个**存在**的环境变量，否则 Codex 启动前就退出。值是什么无所谓。
- 想让某个模型成为默认：在 `config.toml` 顶层写 `model` + `model_provider`。
- 多个模型轮换：给每个模型建一个 profile 文件（`%CODEX_HOME%\<name>.config.toml`），
  用 `codex --profile <name>` 选。注意新版 Codex 不接受在 `config.toml` 里写
  `[profiles.X]` 旧格式。

若想让 Codex 的 `/model` 选单也显示这些模型，需要 `model_catalog_json`。
仓库不带 catalog——它依赖 Codex 版本的 schema，容易过期。需要时用
`GET /v1/models` 的返回自己生成，字段照 Codex 官方示例。

## Cursor

Cursor 的 BYOK 设置不在 UI 里给本地地址，用脚本写它的 SQLite 存储：

```powershell
python clients\cursor-point-to-bridge.py --port 18490
python clients\cursor-point-to-bridge.py --port 18490 --models glm-5.3,deepseek-v4-pro
python clients\cursor-point-to-bridge.py --restore
```

它做的事：

| 键                                           | 值                              |
| -------------------------------------------- | ------------------------------- |
| `applicationUser.useOpenAIKey`               | `true`                          |
| `applicationUser.openAIBaseUrl`              | `http://127.0.0.1:<port>/v1`    |
| `applicationUser.aiSettings.userAddedModels` | 追加模型 id                     |
| `ItemTable[cursorAuth/openAIKey]`            | `wb-bridge-local`（明文兜底行） |

为什么需要那个明文兜底行：Cursor 正常用 Electron safeStorage 加密 OpenAI key，外部无法伪造；
它的 `hydrateKey()` 在密文缺失时回落到旧版明文行。桥接忽略鉴权，所以占位值足够。

脚本行为：关 Cursor → 备份 `state.vscdb{,-wal,-shm}` → 写入 → 只读校验 → 失败自动回滚 → 重开 Cursor。
如果 Cursor 改了存储键名，脚本在**写入前**中止，不会留下坏库。

Cursor 同一时间只认一个 base URL，所以两个版本之间切换要重跑脚本换端口
（`--restore` 后再 `--port 18491`）。

## 任意 OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:18490/v1", api_key="local")

# 普通对话
r = client.chat.completions.create(
    model="glm-5.3-flash",
    messages=[{"role": "user", "content": "你好"}],
)
print(r.choices[0].message.content)

# 工具调用
tools = [{"type": "function", "function": {
    "name": "get_time", "description": "current time",
    "parameters": {"type": "object", "properties": {}}}}]
r = client.chat.completions.create(model="glm-5.3", messages=[{"role": "user", "content": "几点了"}],
                                   tools=tools)
print(r.choices[0].message.tool_calls)
```

注意：**流式参数 `stream=True` 能收 SSE，但内容是「攒齐后一次性发出」**（见 `LIMITATIONS.md`）。
如果你的代码依赖逐 token 更新 UI，观感会很差；依赖最终结果则完全没问题。

## LangChain / LlamaIndex / Dify 等

任何接受 `base_url` + `api_key` 的 OpenAI 兼容客户端都能接。填：

- Base URL: `http://127.0.0.1:18490/v1`
- API Key: 任意非空
- Model: `GET /v1/models` 里的 `id`

模型名**不要写死**在代码里。WorkBuddy 会换 id，写死了就等着 400。

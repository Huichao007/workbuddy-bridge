# 排错手册

先跑 `python doctor.py`。它的七步顺序就是故障域顺序，FAIL 在第一处停下修，别跳。

```
1. installation     安装目录 → WBIPC 客户端库 → WorkBuddy.exe
2. desktop session  endpoint.json → 管道握手（真开一次）
3. bridge           端口 → /health → /v1/models
```

---

## 启动阶段

### `FATAL: WBIPC client library not found`

`wbpaths.py` 没找到安装目录。它依次尝试：`WORKBUDDY_HOME` → 运行中的 `WorkBuddy.exe` 进程路径
→ 卸载注册表 → 常见安装目录。

```powershell
$env:WORKBUDDY_HOME = "D:\Apps\WorkBuddy"   # 指向含 WorkBuddy.exe 的那一层
python doctor.py
```

常见误导：指向了 `WorkBuddy\resources` 或 `WorkBuddy\WorkBuddy.exe`。要的是**目录**。

### `FATAL: cannot import workbuddy_ipc`

目录找到了但库不在预期相对路径下（桌面端版本变了或安装不完整）。
`doctor.py` 会打印它实际找的完整路径；对照安装目录看是否存在
`resources\app.asar.unpacked\resources\plugins\workbuddy-builtin\skills\library\workbuddy_ipc\`。

这个目录缺失通常意味着安装包被裁剪或版本过旧。**重新安装桌面端**，不要在仓库里塞一份替代品。

### `python` 找不到

`scripts\start-bridge.ps1` 只认 PATH 里的 `python` / `py` / `python3`。
装 Python 3.9+ 并勾选 "Add to PATH"，或先 `where.exe python` 确认。

---

## 连接阶段

### `/health` 里 `wbipc.available = false`

按可能性排序：

1. **桌面端没开** → 打开并登录，再跑 `doctor.py`。
2. **开了但没登录** → 登录后管道才会 `wb.request` 就绪。日志里会看到
   `host pipe wb.request unavailable (logged out?)`。
3. **`endpoint.json` 陈旧** → 桌面端上次异常退出留下的。重启桌面端即可。
4. **配置目录不对** → 桌面端用了非默认目录（比如把配置搬到了 D 盘）。
   设 `WORKBUDDY_CONFIG_DIR` 指向含 `wbipc\endpoint.json` 的那一层。

### 503 `WorkBuddy 桌面端未运行`

和上一条同源。区别是这条是**请求路径**上的错误：桥接已经试过自动拉起（120 秒冷却内只试一次），
仍失败。手动开桌面端、登录、重发。

### 端口被占

```powershell
Get-NetTCPConnection -LocalPort 18490 -State Listen | Select-Object OwningProcess
Get-Process -Id <PID>
```

多半是上一次的 `bridge.py` 没退干净。`python setup.py stop` 停掉它，或者 `python setup.py --ports 18500,18501` 换一组端口（setup 会把客户端配置一起改好）。

---

## 请求阶段

### 400 `missing model` / 模型 id 不认识

清单过期。**别照抄 README 里的 id**：

```powershell
curl.exe http://127.0.0.1:18490/v1/models
```

用返回结果里的 `id`。OpenCode 用户直接 `python tools\sync-opencode.py --apply`。

### 400 提到 `reasoning_effort`

GLM-5.1 / GLM-5.0-Turbo 等模型要求显式档位。桥接会按产品配置自动补齐；
仍然报错说明产品配置读不到（见上），桥接手里没有 `supportedEfforts` 可用。
重启桌面端让配置重新落盘。

### 502 `E_UPSTREAM upstream request failed`

上游瞬时失败。桥接对**非超时**的 `E_UPSTREAM` 自动重试一次。
连续出现时抓快照：

```powershell
$env:WB_BRIDGE_DUMP = "err"
python bridge.py
```

`dumps-<port>\upstream-err-*.json` / `wbipc-err-*.json` 里有出站 body 与错误码。

### 502 `E_PAYLOAD_TOO_LARGE`

响应体超过桌面端硬上限（约 640 KiB）。**这是设计边界**，见
[`LIMITATIONS.md`](LIMITATIONS.md) 第 2 条。把长输出拆成多轮。

### 请求体积过大，桥接直接 400

桥接允许的单请求 JSON 约 60 MiB（为 base64 帧开销留了余量），超过会明确报字节数。
通常是误把整个仓库塞进上下文了。

---

## 客户端专属

### Codex：`wire_api = "chat" is no longer supported`

```toml
wire_api = "responses"   # 必须是这个
```

### Codex：启动时提示缺少环境变量

`env_key = "WORKBUDDY_API_KEY"` 要求这个变量**存在**，值无所谓：

```powershell
$env:WORKBUDDY_API_KEY = "wb-bridge-local"
```

### Cursor：模型列表里没有 WorkBuddy 的模型

1. Cursor 必须**完全退出**再跑脚本（它退出时会用内存里的设置覆盖数据库）。
2. `python clients\cursor-point-to-bridge.py` —— 看它是否打印 `DONE`。
3. 校验失败会自动回滚，脚本会告诉你哪一项没写进去。
4. Cursor 大版本更新可能改了存储键名，脚本会在写入前中止。这种情况提 issue 带版本号。

### OpenCode：配置校验不通过

`opencode` 对 provider schema 很严格。v2 用 `package` + `settings`，v1 用 `options`。
混用会直接被拒。用 `clients\opencode.json` 里对应你版本的那份。

---

## 还是不行

收集这四样再提问，能省掉一半来回：

1. `python doctor.py` 的完整输出
2. WorkBuddy 桌面端版本号
3. `bridge.log` 最后 50 行
4. `WB_BRIDGE_DUMP=err` 后复现一次的 `dumps-<port>\` 文件名列表

**不要贴 API key、cookie、完整对话内容。** 本项目正常运行时不需要它们，贴出来只会泄露你自己的东西。

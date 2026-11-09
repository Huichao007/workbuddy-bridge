# 运维

这个目录不属于产品运行时，是**维护这个仓库本身**用的。删掉它不影响桥接工作。

## daily.py

每天一次的运营巡检，本机跑：

```powershell
python ops\daily.py            # 完整检查（含一次真实模型调用）
python ops\daily.py --fast     # 跳过真实调用
```

检查四组事，任何 `fail` 都会以非零码退出：

| 组           | 查什么                                                                               |
| ------------ | ------------------------------------------------------------------------------------ |
| service      | 18490 在不在、wbipc 可用不可用、真发一次请求能不能回话                               |
| repository   | 本地 main 和 origin/main 有没有漂移、main 上最后一次 CI 是否通过、有没有挂着的 issue |
| product page | README 是否还写着 OpenCode / Codex / 安装命令 / 验证命令                             |

报告写到 `ops/reports/report-<日期>.md`（已在 `.gitignore` 里，因为含本机绝对路径）。

**为什么要查 README**：项目主页是唯一的转化入口。一次重构把那段删掉，
访客就再也看不出「装了能用 OpenCode 和 Codex」，而这种退化不会让 CI 变红
——除非专门有人盯着。CI 里也有一模一样的检查。

## install-daily.ps1

把上面的检查注册成每天 09:30 的计划任务：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ops\install-daily.ps1
powershell ... -Remove
```

以当前用户身份跑（巡检要调桥接，桥接借的是你的桌面端登录态），**不要用 SYSTEM**。

## Token

仓库检查需要读权限。计划任务没有有用的环境变量，所以 token 放在：

```
D:\opencode\secrets\workbuddy-bridge-ops.token
```

已通过 ACL 限制为仅当前用户可读。读取顺序是：环境变量 `WB_GH_TOKEN` /
`GH_TOKEN` / `GITHUB_TOKEN` → 上面这个文件 → `gh auth token`。
前三种都没有时，巡检会降级：服务检查照做，仓库检查标记为 `warn` 而不是失败。

不要把这个文件提交进仓库。仓库的 `.gitignore` 已经拒绝 `*.key`；这个文件在
仓库目录之外，不受影响。

# 安全

## 设计上的安全边界

- **只监听回环地址**。默认 `127.0.0.1:18490`（第二个实例 18491，以此类推）。桥接**没有鉴权**，这是刻意设计：
  它只在单机单用户场景下工作。把 `WB_BRIDGE_HOST` 改成 `0.0.0.0` 等于把你账户的额度
  向同网段所有人开放——真要这么用，先加反向代理 + token 校验。
- **不接触凭证**。桥接不读 cookie、不读 token、不写任何登录信息。
  它只是请求桌面端进程"帮我发这个 HTTP 请求"，鉴权发生在桌面端内部。
- **不记录正文**。`bridge.log` 只写时间、模型名、消息条数、状态码、路径。
- **快照只在显式开启时产生**，且 `dumps-<port>/` 只保留最近 300 个文件。
- **安装脚本只写三处**：`instances.json`、客户端配置文件（写前备份）、两个计划任务。
  不改 WorkBuddy 安装目录，不结束它的进程，不读它的登录数据。

## 报告漏洞

请用 GitHub 的 **Private vulnerability reporting**（Security 选项卡 → Report a vulnerability），
不要开公开 issue。

请包含：复现步骤、影响（谁能利用、能拿到什么）、你的 Windows 与 WorkBuddy 版本。
**不要在报告里贴真实 key 或完整对话内容。**

## 这个项目不做什么（重要）

明确拒绝的几类功能，避免有人提 issue 期待它实现：

- 修改 WorkBuddy 安装包 / 重算完整性哈希 / 绕过签名校验
- 多账号池、自动换号、额度分摊
- 把本机桥接暴露成公网服务
- 抓取或复用桌面端的登录凭证

理由见 [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) 与 README 的合规声明。

## 如果你 fork 或二次分发

- 不要把 `relay-models.json`、`instances.json`、`.env`、`*.key`、`dumps-*/` 提交进仓库（`.gitignore` 已覆盖）。
- 不要在示例/文档里写真实的中转地址与 key。
- 保留 README 里的合规声明——使用者有权知道风险。

# 参与

## 提 issue 前

1. 跑 `python doctor.py`，贴完整输出。
2. 贴 WorkBuddy 桌面端版本、Windows 版本、Python 版本；两个版本都装了的说明是哪一份出问题。
3. 如果有 `dumps-<port>/` 快照，只说文件名和错误码就够了，**不要贴 body 全文**（可能含你的对话内容）。
4. 先翻 [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) 和
   [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md)。"没有逐字流式""响应有 640KB 上限"是已知设计，
   不是待修 bug。

## 提 PR

- 保持**纯标准库**。引入依赖需要有很强的理由，并且要解释为什么不能用标准库做到。
- 不要提交任何真实密钥、中转地址、个人路径（`C:\Users\xxx`、`D:\someone\...`）。
  `wbpaths.py` 已经处理了路径探测，别把本机路径写回代码。
- 不要提交 `instances.json`、`dumps-*/`、`*.log`、`relay-models.json`。
- 改**实例发现 / 端口分配 / 客户端配置合并**时，请说明这两种场景都试过：
  只有一个版本、两个版本都登录。这两条路径的失败方式完全不同。
- 改协议相关代码时，手写验证步骤放进 PR 描述：哪个客户端、哪个模型、什么现象。
- 不接受的改动见 [`SECURITY.md`](SECURITY.md) 的"这个项目不做什么"。

## 提交信息

一句话说清"改了什么、为什么"。中文英文都行。

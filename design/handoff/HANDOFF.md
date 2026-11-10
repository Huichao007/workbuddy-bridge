# wb-bridge · 设计交接（网站）

> 生成于 2026-11-10T05:22:51.351Z · 设计稿 `D:\projects\workbuddy-bridge\design\wb-bridge.fig`
> 本目录由 `design-system/design.mjs handoff` 生成，可重复执行；改设计稿后重新生成即可。

## 1. 屏清单

| 屏 | 尺寸 | 视觉稿 | HTML 预览 | JSX |
| --- | --- | --- | --- | --- |
| 02 架构图 Architecture | 1240×648 | [png](screens/02-architecture.png) | [html](screens/02-architecture.html) | [jsx](screens/02-architecture.jsx) |

## 2. 设计变量（唯一来源）

CSS 变量：`tokens/tokens.css`；小程序：`tokens/tokens.wxss`（已 px→rpx）；Tailwind：`tokens/tokens.tailwind.css`；DTCG：`tokens/design.tokens.json`。

### 颜色

| 变量 | 值 |
| --- | --- |
| `--color-bg` | #08090A |
| `--color-surface` | #0F1011 |
| `--color-surface-2` | #191A1B |
| `--color-surface-3` | #28282C |
| `--color-line` | #23252A |
| `--color-line-soft` | #18191A |
| `--color-text-1` | #F7F8F8 |
| `--color-text-2` | #D0D6E0 |
| `--color-text-3` | #8A8F98 |
| `--color-text-4` | #62666D |
| `--color-brand` | #7170FF |
| `--color-brand-soft` | #5E6AD2 |
| `--color-brand-dim` | #16172B |
| `--color-brand-ink` | #A8A8FF |
| `--color-ok` | #27A644 |
| `--color-warn` | #F5A623 |
| `--color-on-brand` | #FFFFFF |
| `--color-on-solid` | #08090A |

### 间距 / 圆角 / 字号

| 变量 | 值 |
| --- | --- |
| `--spacing-s1` | 4px |
| `--spacing-s2` | 8px |
| `--spacing-s3` | 12px |
| `--spacing-s4` | 16px |
| `--spacing-s5` | 20px |
| `--spacing-s6` | 24px |
| `--spacing-s7` | 32px |
| `--spacing-s8` | 40px |
| `--spacing-s9` | 48px |
| `--spacing-s10` | 64px |
| `--spacing-s11` | 96px |
| `--spacing-s12` | 128px |
| `--radius-sm` | 5px |
| `--radius-md` | 10px |
| `--radius-lg` | 16px |
| `--radius-full` | 999px |
| `--text-fs1` | 11px |
| `--text-fs2` | 12px |
| `--text-fs3` | 13px |
| `--text-fs4` | 15px |
| `--text-fs5` | 17px |
| `--text-fs6` | 22px |
| `--text-fs7` | 28px |
| `--text-fs8` | 40px |
| `--text-fs9` | 56px |
| `--leading-display` | 1.05px |
| `--leading-title` | 1.15px |
| `--leading-body` | 1.5px |

## 3. 组件（设计稿里的可复用件）

- 暂无可复用组件（设计稿里还没有 Component）；重复出现的结构见 `component-map.json`

## 4. 落地规则

- 样式：`tokens/tokens.css` 直接引，或 `tokens/tokens.tailwind.css` 接 Tailwind v4
- 结构：`screens/*.html` 是可直接打开的静态起点（已注入 token），`screens/*.jsx` 给 React 用
- 颜色/字号/间距/圆角一律走变量，禁止魔法数字
- 校验：浏览器 375×812 截图与 `screens/*.png` 对照

## 5. lint 体检

error 0 · warning 9 · info 124（共 133 条，完整列表见 `lint.json`）

- [warning] min-text-size: Text size 11px is below minimum 12px
- [warning] min-text-size: Text size 11px is below minimum 12px
- [warning] min-text-size: Text size 11px is below minimum 12px
- [warning] min-text-size: Text size 11px is below minimum 12px
- [warning] min-text-size: Text size 11px is below minimum 12px
- [warning] min-text-size: Text size 11px is below minimum 12px
- [warning] min-text-size: Text size 11px is below minimum 12px
- [warning] min-text-size: Text size 11px is below minimum 12px

> 无 error，可进入开发。

## 6. 开发顺序（照此推进）

1. 把 `tokens/` 落到项目里，先跑通一个空页面（背景/文字/字号都对）
2. 按屏清单从主屏开始：先静态结构 → 再绑变量 → 再接数据
3. 每块做完立刻和 `screens/<屏>.png` 对照（375 宽），差异记进项目 README
4. 数据接入后再跑一次对照，确认涨跌色、暗色对比度没走样
5. 交付前 `design check <fig>` 确认设计稿 lint 干净，代码侧 grep 确认无硬编码 hex

## 7. 设计稿续改

```bash
# 打开设计稿改完保存后，重新生成交接物（覆盖本目录）
design handoff "D:\projects\workbuddy-bridge\design\wb-bridge.fig" --platform web --out "D:\projects\workbuddy-bridge\design\handoff"
```

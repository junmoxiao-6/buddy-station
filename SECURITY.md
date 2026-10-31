# 安全策略

## 本项目**不做**什么

这些是刻意设计的边界，不是"还没实现"：

| 行为 | 状态 | 原因 |
|---|---|---|
| 读取并解密 WorkBuddy 客户端的加密登录态文件 | ❌ 不做 | 那是绕过客户端的安全设计；本项目只走你本人扫码授权 |
| 自动下载并覆盖自身代码 | ❌ 不做 | 等于给工具开远程执行口子，且你无法审计装了什么 |
| 注册系统计划任务 / 修改系统设置 | ❌ 不做 | 只输出参数，注册由你执行 |
| 上传数据 / 遥测 / 回调 | ❌ 不做 | 没有任何统计上报 |
| 批量刷分 / 多账号批量操作 | ❌ 不做 | 只操作当前授权账号 |
| 在日志或输出里打印令牌 | ❌ 不做 | `acquire-rt --show` 是唯一例外，且需显式加参数 |

## 会写入的位置

| 路径 | 内容 |
|---|---|
| `~/.workbuddy/auth/workbuddy.json` | 令牌（你扫码授权后写入，续期时更新） |
| `~/.workbuddy/auth/device_state.json` | 一次性授权 state |
| `<data-dir>/logs/*.jsonl`、`last_result.json` | 运行记录（只有状态与数字） |
| `<data-dir>/logs/notify_journal.jsonl` | 通知台账（不含 URL） |

`<data-dir>` 见 README「数据目录」。除此之外不碰任何路径。

## 会发请求的域名

- `www.workbuddy.cn` —— 签到 / 旅行业务接口
- `copilot.tencent.com` —— OAuth 设备授权与令牌续期
- `www.codebuddy.cn` —— 授权的 Origin/Referer
- 版本检查：`pypi.org` / `api.github.com`（只读 GET）
- 通知：**你自己配置的**渠道地址（程序里无硬编码通知域名）

## 令牌泄露怎么处置

1. 在 WorkBuddy 客户端**重新登录一次** —— 旧会话会作废（服务端返回 `Session not active`）
2. `buddy-station acquire-rt --clear-rt` 清掉本地残留
3. 重新 `buddy-station login start` 授权，再重新导出
4. 如果令牌进过 CI secret：立刻在平台里轮换该 secret

## 报告漏洞

请**不要**在公开 issue 里贴令牌、uid 或完整请求头。用 GitHub 的
[私密漏洞报告](https://github.com/your-name/buddy-station/security/advisories/new)，
或发 issue 只说现象（例如"某处会把令牌写进日志"），细节我们私下沟通。

48 小时内会有人回应。

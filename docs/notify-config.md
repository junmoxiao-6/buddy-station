# 通知配置

通知是**可选增强项**：没配也能正常签到，配了只是让失败/临界情况主动找你。

## 配置文件位置

按以下顺序找第一个存在的：

1. 环境变量 `BUDDY_STATION_NOTIFY_CONFIG` 指定的路径
2. `<data-dir>/notify_config.json`（标准位置）
3. `~/.workbuddy/notify_config.json`（兼容早期版本）

`<data-dir>` 见 README 的「数据目录」一节。查看实际生效路径与就绪状态：

```bash
buddy-station notify --status
```

## 最小示例

```json
{
  "enabled": true,
  "success_notify": false,
  "channels": [
    { "type": "bark", "url": "https://api.day.app/你的KEY" },
    { "type": "feishu", "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx" }
  ]
}
```

| 字段 | 默认 | 说明 |
|---|---|---|
| `enabled` | `true` | 总开关；`false` 时一条都不发 |
| `success_notify` | `false` | 签到成功是否也推（默认只在异常时打扰你） |
| `channels` | `[]` | 渠道数组，可放多个，逐个尝试 |

单个渠道里加 `"enabled": false` 可单独关掉。

## 支持的渠道

| `type` | 必填字段 | 说明 |
|---|---|---|
| `bark` | `url` | iOS 推送。`url` 就是 `https://api.day.app/<key>`，后缀别加 |
| `feishu` | `webhook` | 飞书群机器人 |
| `wecom` | `webhook` | 企业微信群机器人 |
| `dingtalk` | `webhook` | 钉钉群机器人，用「自定义关键词」校验（关键词填 `Buddy`），**不加签** |
| `telegram` | `token`、`chat_id` | Bot Token 与目标会话 ID |
| `slack` | `webhook` | Slack Incoming Webhook |
| `discord` | `webhook` | Discord Webhook |
| `pushplus` | `token` | PushPlus（微信推送） |
| `serverchan` | `sendkey` | Server 酱 |
| `smtp` | `host`、`from`、`to`（可选 `port`/`user`/`password`/`ssl`） | 邮件。`to` 可以是字符串或数组 |
| `webhook` | `url`（可选 `headers`） | 通用 JSON POST，体为 `{title, body, level, source, ts}` |
| `desktop` | — | **只写本地台账**（不弹系统通知、不起子进程） |

### 各渠道示例

```json
{
  "enabled": true,
  "success_notify": false,
  "channels": [
    { "type": "bark",     "url": "https://api.day.app/AbCdEf123456" },
    { "type": "feishu",   "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/9f2c..." },
    { "type": "wecom",    "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." },
    { "type": "dingtalk", "webhook": "https://oapi.dingtalk.com/robot/send?access_token=..." },
    { "type": "telegram", "token": "123456:ABC-DEF...", "chat_id": "987654321" },
    { "type": "slack",    "webhook": "https://hooks.slack.com/services/T00/B00/xxx" },
    { "type": "discord",  "webhook": "https://discord.com/api/webhooks/123/xxx" },
    { "type": "pushplus", "token": "your_pushplus_token" },
    { "type": "serverchan", "sendkey": "SCT123456Txxx" },
    {
      "type": "smtp",
      "host": "smtp.example.com",
      "port": 465,
      "ssl": true,
      "from": "bot@example.com",
      "to": ["you@example.com"],
      "user": "bot@example.com",
      "password": "your_smtp_password"
    },
    {
      "type": "webhook",
      "url": "https://your-endpoint/hook",
      "headers": { "Authorization": "Bearer xxx" }
    }
  ]
}
```

## 什么时候会推

| 触发条件 | 级别 |
|---|---|
| 退出码 `10`（鉴权失败、账号不符） | `error` |
| 退出码 `30`（上游异常） | `error` |
| 退出码 `20`（无可用通道） | `error` |
| 距第 7 天大奖**还差 1 天** | `warn` |
| 签到成功 | `info`，**仅当** `success_notify: true` |

`dingtalk` 用关键词校验而非加签：加签要 HMAC + Base64，容易被静态扫描判成「编码/混淆」，
收益也低——把机器人关键词设成 `Buddy` 就够了。

## 排错

```bash
buddy-station notify --status     # 哪些渠道就绪（URL 自动脱敏）
buddy-station notify --test       # 真发一条，看返回
```

- **状态显示就绪但收不到**：先看 `notify --test` 的返回码，再检查手机端是否静音/折叠
- **飞书/企微返回 200 但没消息**：看响应体里的 `code` / `errcode` 是不是 `0`
- **想临时静音**：本次加 `--no-notify`，或把配置里 `enabled` 改 `false`

## 隐私

- 通知只发往**你自己填的地址**，程序里没有任何硬编码的通知域名
- 推送正文只有「动作 / 结果 / 余额 / 时间」，**不含令牌**
- `notify --status` 与日志里的 URL 会自动脱敏（`key=xxx***`、`api.day.app/xxxx***`）
- 台账 `notify_journal.jsonl` 只记「时间 / 渠道类型 / 成功与否」，不记 URL

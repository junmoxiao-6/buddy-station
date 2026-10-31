---
name: buddy-station-guardian
version: "2.0.0"
description: >
  当用户说「签到 / 领积分 / 每日签到 / 派猫猫 / 猫猫旅行 / 领旅行奖励 / 查连签 /
  云端自动签到 / 一键自动化 / 定时签到 / 签到自检」时使用。
  完成 WorkBuddy 加油站的每日签到与猫猫旅行闭环，并可把定时任务一次定下来。
allowed-tools: Bash
---

# Buddy 加油站值守

只干三件事，边界说清楚：

1. **签到** —— 每日领积分（连签有加成，连续第 7 天有大奖）
2. **派猫** —— 猫猫旅行闭环：**先领到店奖励，再派新的**（避免只派不领）
3. **守护** —— 记录每日结果，报告「连签 N 天 / 距大奖还差 M 天」

实现是一份零依赖 Python 包，技能形态只是它的一个外壳：命令 `buddy-station <动作>`
与 `python -m buddy_station <动作>` 完全等价。

---

## 被调用时怎么做（四步，缺一步算没做完）

### 第 1 步 建定时任务（幂等，不重复建）

先查是否已有：

```
automation_update(mode="list")
```

- 已有名字含「Buddy 加油站」的活动任务 → **跳过**，直接第 2 步
- 没有 → 用 `buddy-station setup` 输出里的 `schedule.suggestion.params` 原样传：

```
automation_update(mode="create", **params)
```

（`params` 里已算好 `name` / `rrule` / `prompt`，不要现场拼，容易拼错。）

### 第 2 步 确认凭据

```bash
buddy-station auth
```

| 输出 | 含义 | 下一步 |
|---|---|---|
| `configured: true` | 有可用凭据 | 直接第 3 步 |
| 带 `auth_url` | 需要你扫码一次 | 把链接单独一行贴给用户，**本次结束**，并说明「未签到，不是失败」 |
| `configured: false` 且云端 | 云端自建二维码会被服务端拒收 | 走 `buddy-station login adopt '<客户端发起的链接>'` |

**禁止** `login poll --wait`：无人值守任务里干等 5 分钟，用户只会看到转圈。

### 第 3 步 执行

```bash
buddy-station run
```

一次完成：签到 → 到店领取 → 空闲派遣 → 连签统计。可反复跑（幂等）。

### 第 4 步 汇报（固定三行）

```
签到：<checkin.result>（<balance> 分）
猫猫：<travel.result>（到店 <arrive_at>）
连签：<streak.streak> 天，距大奖还差 <streak.days_to_bonus> 天
```

失败必须写清退出码与原因，**禁止把失败伪装成成功**。

---

## 命令清单

```bash
buddy-station run                  # 签到 + 遛猫（日常就这一条）
buddy-station checkin              # 只签到
buddy-station travel               # 只处理猫猫旅行（先领后派）
buddy-station probe                # 只读：通道 / 今日状态 / 身份
buddy-station diagnose             # 只读全量自检（别名 doctor）
buddy-station report               # 读本地记录，输出连签汇总
buddy-station setup                # 环境探测 → 凭据 → 签到 → 定时任务参数
buddy-station auth                 # 凭据自助：有令牌直接确认，没有就出授权链接
buddy-station acquire-rt --show     # 导出长效 refresh token（CI secret 用）
buddy-station update               # 只读检查有没有新版
buddy-station login start|adopt|poll|status   # 设备授权
buddy-station notify --status      # 通知渠道自检
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--channel auto\|wbipc\|token_file\|rt\|skill_token` | 强制通道（默认 auto） |
| `--expect-uid <uid>` | 多账号护栏：账号不符直接 exit 10，绝不误操作别的账号 |
| `--location 1..4` | 固定派遣地点；不传按日期 4 天轮换 |
| `--no-notify` | 本次不推送通知 |
| `--data-dir DIR` | 运行数据目录（便携模式） |

---

## 四种通道

| 通道 | 依赖 | 适用 |
|---|---|---|
| `wbipc` | WorkBuddy 客户端在运行且已登录 | 桌面端零配置 |
| `token_file` | `~/.workbuddy/auth/workbuddy.json` | 本机定时任务 |
| `rt` | 环境变量 `WORKBUDDY_RT`（refresh token） | **GitHub Actions / CI** |
| `skill_token` | 宿主注入 `X-Skill-Token` | 平台托管运行时 |

`auto` 顺序：`wbipc` → `token_file` → `rt`（仅当注入）→ `skill_token`。

云端授权两条路：

- **正路（adopt）**：桌面客户端点「重新发起登录」→ 复制链接 → `buddy-station login adopt '<链接>'` → 用户扫码 → `login poll`
- **备选（start）**：`buddy-station login start` 自己出链接（部分平台会拒收云端自建会话）

---

## 输出与退出码

每次执行都输出**一行 JSON**，并写一份到 `<data-dir>/logs/last_result.json`。

| 退出码 | 含义 | 定时任务该怎么办 |
|---|---|---|
| `0` | 成功 / 幂等跳过（今天已签也返回 0） | 无需处理 |
| `10` | 需要人工（鉴权失败、账号不符） | 通知人 |
| `20` | 没有可用通道 | 补凭据 |
| `30` | 上游异常（5xx、超时、响应畸形） | 可重试 |

---

## 定时任务

`buddy-station setup` 会输出**参数**（解释器、参数、工作时间点），**不会**替你注册：

- Windows：任务计划程序，模板见 `docs/scheduling.md`
- Linux/macOS：crontab / systemd timer，同上
- 云端：用 `schedule.suggestion.params` 调 `automation_update`

每 6 小时一轮（`FREQ=HOURLY;INTERVAL=6`）是推荐值：猫旅途 1–4 小时，
6 小时间隔能保证"到店后必被领"，再密只是白烧额度。

---

## 安全边界

| 行为 | 是否发生 |
|---|---|
| 读取并解密客户端加密登录态 | **不做** |
| 读 `~/.workbuddy/auth/workbuddy.json` | 会（这是**你自己授权后**落盘的令牌） |
| 令牌出现在 stdout / 日志 / 结果 JSON | 不会（`acquire-rt --show` 是唯一例外，需显式加参数） |
| 令牌发往非官方域名 | 不会 |
| 上传任何数据 / 遥测 | 不会 |
| 自动下载并覆盖自身代码 | 不会（`update` 只比版本号） |

只操作当前登录账号；不批量、不刷分。

# buddy-station

<p align="center"><img src="icon.png" width="96" alt="buddy-station"></p>

> WorkBuddy「Buddy 加油站」每日签到 + 猫猫旅行闭环的**零依赖命令行工具**。
> 一条命令跑完签到、到店领奖、再派出；被调用一次就能把定时任务定下来。

[![CI](https://github.com/your-name/buddy-station/actions/workflows/ci.yml/badge.svg)](https://github.com/your-name/buddy-station/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](pyproject.toml)

> **第一次用？** 克隆后先跑 `python scripts/set_repo.py <你的GitHub用户名>`，
> 把 README 徽章、PyPI 链接、Issue 模板里的 `your-name` 一次性换成你自己的（共 14 处）。

```console
$ buddy-station run
{"ok": true, "action": "run", "checkin": {"result": "already", "streak_days": 30},
 "travel": {"result": "daily_limit", "arrive_at": 1793512800},
 "balance": 3000, "summary": "签到:already / 猫猫:daily_limit", ...}
```

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [快速开始](#快速开始)
- [它是怎么工作的](#它是怎么工作的)
- [命令参考](#命令参考)
- [配置](#配置)
- [部署成定时任务](#部署成定时任务)
- [输出格式与退出码](#输出格式与退出码)
- [常见问题](#常见问题)
- [安全与隐私](#安全与隐私)
- [项目结构](#项目结构)
- [开发](#开发)

---

## 它解决什么问题

每天要手动点的三件事，它一次做完：

| 任务 | 细节 | 为什么需要自动化 |
|---|---|---|
| **签到** | 每日领积分，连签有加成，连续第 7 天有大奖 | 断签就清零，忘了很亏 |
| **猫猫旅行** | 猫到店后要领奖励，领完才能派新的 | 只派不领 = 奖励白丢 |
| **连签守护** | 记录每天结果，算「还差几天到大奖」 | 手动记不现实 |

设计上的几条硬规则：

- **先领后派**：到店奖励没领掉之前绝不派新猫，避免"奖励过期"
- **幂等**：今天已经签过就返回 `already` 且退出码 `0`，定时任务可以一天跑 4 次而不出错
- **失败不伪装**：签到成功但猫没派出去 → 退出码 `30`，不会静悄悄当成功
- **只检查不自动升级**：版本检查只发一次 GET，**不下载、不解压、不覆盖**自身代码

---

## 快速开始

### 前置条件

- Python **3.10+**（用到了 `X | None` 这类写法）
- 一个已登录的 WorkBuddy 账号
- 无需任何第三方库（`pip install` 不会拉依赖）

### 方式一：从源码安装（推荐）

```bash
git clone https://github.com/your-name/buddy-station.git
cd buddy-station
pip install -e .
buddy-station diagnose      # 先做只读自检，确认环境
```

### 方式二：不安装，直接跑

```bash
git clone https://github.com/your-name/buddy-station.git
cd buddy-station
python -m buddy_station diagnose
```

> 不安装也能跑，但 `pip install -e .` 之后才能用 `buddy-station` 这个短命令。

### 方式三：只用技能形态（WorkBuddy 技能目录）

```bash
git clone https://github.com/your-name/buddy-station.git
cp -r buddy-station/skill ~/.workbuddy/skills/buddy-station-guardian
```

技能里的 `scripts/checkin.py` 是**引导脚本**，会转发到本包（需先 `pip install` 或用仓库内路径）。
这样技能形态与 CLI 形态共用一份实现，不会出现"两边行为不一致"。

### 第一次运行

```bash
# 1) 只读自检：看清楚通道、令牌、今日状态，不做任何写操作
buddy-station diagnose

# 2) 如果提示没有凭据，走一次授权（扫码）
buddy-station login start
#    → 输出 auth_url，浏览器打开并登录
buddy-station login poll
#    → 拿到令牌，落在 ~/.workbuddy/auth/workbuddy.json

# 3) 正式跑一次
buddy-station run
```

桌面端通常**不需要**第 2 步：只要 WorkBuddy 客户端在运行且已登录，`wbipc` 通道会自动可用。

---

## 它是怎么工作的

```
                    ┌──────────────────────────────┐
   一次 run 做三件事  │  1. 签到（幂等）              │
                    │  2. 猫到店？→ 先领奖励        │
                    │  3. 猫空闲？→ 派新猫          │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  通道层：凭据从哪来            │
                    │  wbipc → token_file → rt →    │
                    │  skill_token（auto 按序尝试）  │
                    └──────────────────────────────┘
```

### 四种通道，覆盖三种环境

| 通道 | 依赖 | 需要客户端运行 | 典型场景 |
|---|---|:--:|---|
| `wbipc` | 客户端注入的本地管道 | ✅ | 桌面端，**零配置** |
| `token_file` | `~/.workbuddy/auth/workbuddy.json` | ❌ | 本机计划任务、持久沙箱 |
| `rt` | 环境变量 `WORKBUDDY_RT` | ❌ | **GitHub Actions / 任何 CI** |
| `skill_token` | 宿主注入 `X-Skill-Token` | — | 平台托管运行时 |

`auto` 的尝试顺序：`wbipc` → `token_file` → `rt`（仅当注入了 `WORKBUDDY_RT`）→ `skill_token`。
想强制某一条：`--channel rt`。

> **为什么 `rt` 单独存在**：CI 里最方便的是"一个 secret 字符串"。
> refresh token 正好就是这个字符串——每次运行用它换一个短期 access，用完即弃。
> 环境变量来源**不落盘**，secret 不会被复制进沙箱磁盘或日志。

### 猫猫旅行的状态机

```
        ┌──────┐  派猫   ┌───────────┐  旅途 1-4h  ┌─────────┐
        │ idle │ ──────► │ traveling │ ─────────► │ arrived │
        └──────┘         └───────────┘            └────┬────┘
            ▲                                          │
            │              领奖励（先领）               │
            └──────────────────────────────────────────┘
```

- `traveling`：什么都不做，只报告预计到店时间
- `arrived`：**先领奖励**，领完若还能派就立刻派
- `idle` 且 `daily_limit_reached=true`：今天额度用完，正常结束（退出码 0，不是错误）

---

## 命令参考

| 命令 | 作用 | 是否写操作 |
|---|---|:--:|
| `run` | 签到 + 遛猫 + 连签统计（**日常就这一条**） | ✅ |
| `checkin` | 只签到 | ✅ |
| `travel` | 只处理旅行（先领后派） | ✅ |
| `probe` | 只读：通道 / 今日状态 / 身份 | ❌ |
| `diagnose`（别名 `doctor`） | 只读全量自检：版本 / 端 / 通道 / 令牌 / 通知 | ❌ |
| `report` | 读本地 JSONL，输出连签汇总 | ❌ |
| `setup` | 环境探测 → 凭据 → 签到 → 输出定时任务参数 | ✅ |
| `auth` | 凭据自助：有令牌直接确认，没有就出授权链接 | ❌ |
| `acquire-rt` | 导出 / 录入 / 清除长效 refresh token | 可选 ✅ |
| `update` | 只读检查有没有新版 | ❌ |
| `login start\|adopt\|poll\|status` | 设备授权（扫码一次，之后自动续期） | ✅ |
| `notify --status\|--test` | 通知渠道自检 / 发测试消息 | ❌ |

### 常用参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--channel` | `auto` | 强制通道：`wbipc` / `token_file` / `rt` / `skill_token` |
| `--location 1..4` | 按日期轮换 | 固定派遣地点（同一天各机器结果一致） |
| `--expect-uid <uid>` | 无 | **多账号护栏**：账号不符直接 `exit 10`，绝不误操作别的号 |
| `--allow-unverified-uid` | 关 | 取不到 uid 时仍执行（CI 常不注入 uid，需要它） |
| `--out <path>` | 无 | 结果 JSON 额外写一份 |
| `--no-notify` | 关 | 本次不推送通知 |
| `--data-dir DIR` | 平台标准目录 | 便携模式：日志与状态都放这里 |

---

## 配置

### 数据目录

日志、结果快照、通知台账都在这里（**不在**安装目录，因为 pip 安装的包目录可能只读）：

| 平台 | 路径 |
|---|---|
| Windows | `%LOCALAPPDATA%\buddy-station` |
| macOS | `~/Library/Application Support/buddy-station` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/buddy-station` |

覆盖方式：环境变量 `BUDDY_STATION_HOME`，或 `--data-dir`。

```
<data-dir>/
├── logs/
│   ├── daily.jsonl            # 每天一行，供连签统计
│   ├── last_result.json       # 最近一次结果（云端自动化常读这个）
│   └── notify_journal.jsonl   # 通知台账（不含 URL）
```

### 通知（可选）

配置文件：`<data-dir>/notify_config.json`（也兼容 `~/.workbuddy/notify_config.json`）

```json
{
  "enabled": true,
  "success_notify": false,
  "channels": [
    { "type": "bark",   "url": "https://api.day.app/你的KEY" },
    { "type": "feishu", "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx" },
    { "type": "telegram", "bot_token": "123:abc", "chat_id": "456" }
  ]
}
```

支持 12 种渠道：`bark` / `feishu` / `wecom` / `dingtalk` / `telegram` / `slack` /
`discord` / `pushplus` / `serverchan` / `smtp` / `webhook` / `desktop`。
字段细节见 [docs/notify-config.md](docs/notify-config.md)。

验证：

```bash
buddy-station notify --status    # 看哪些渠道就绪（URL 自动脱敏）
buddy-station notify --test      # 真发一条
```

推送时机：鉴权失败（10）、上游异常（30）、距大奖还差 1 天 → 主动推；
签到成功默认静默（`success_notify: true` 可开）。

### 多账号

自动化与令牌都是**账号级**的，一个账号一套：

```bash
# 只在这个 uid 下执行，否则拒绝
buddy-station run --expect-uid <你的uid>

# 看当前能取到哪个 uid
buddy-station diagnose
```

---

## 部署成定时任务

`buddy-station setup` 会打印**参数**（解释器、参数、四个时间点），但**不会**替你注册——
持久化操作应当由你自己确认。

### Windows 任务计划程序

```powershell
$py     = "C:\Path\To\python.exe"
$script = "-m buddy_station run --allow-unverified-uid"
$action = New-ScheduledTaskAction -Execute $py -Argument $script
$t1 = New-ScheduledTaskTrigger -Daily -At 00:05
$t2 = New-ScheduledTaskTrigger -Daily -At 06:05
$t3 = New-ScheduledTaskTrigger -Daily -At 12:05
$t4 = New-ScheduledTaskTrigger -Daily -At 18:05
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "BuddyStation" `
  -Action $action -Trigger @($t1,$t2,$t3,$t4) -Settings $set -Force
```

### Linux / macOS（crontab）

```cron
5 0,6,12,18 * * * /usr/bin/python3 -m buddy_station run --allow-unverified-uid >> ~/.local/share/buddy-station/logs/cron.log 2>&1
```

### GitHub Actions（完全不用开电脑）

见 [.github/workflows/checkin.yml](.github/workflows/checkin.yml)，三步搞定：

1. 本地导出长效令牌：`buddy-station acquire-rt --show`
2. 仓库 **Settings → Secrets → Actions** 新建 `WORKBUDDY_RT`，粘贴上一步的值
3. 启用 workflow（默认每 6 小时跑一次），也可以手动 `Run workflow`

```yaml
- name: Check in
  env:
    WORKBUDDY_RT: ${{ secrets.WORKBUDDY_RT }}
  run: python -m buddy_station run --channel rt --allow-unverified-uid
```

> ⚠️ refresh token 会**轮换**（旧 token 用一次就失效）。文件来源会自动写回；
> CI 的 secret 写不回去，所以失效后需要重新导出一次。

更多部署形态见 [docs/cloud-deploy.md](docs/cloud-deploy.md)。

---

## 输出格式与退出码

标准输出**恒为一行 JSON**（同时写 `<data-dir>/logs/last_result.json`），方便被任何东西消费：

```json
{
  "ok": true,
  "action": "run",
  "channel": "token_file",
  "checkin": { "result": "ok", "credit": 100, "streak_days": 31 },
  "travel": { "result": "traveling", "arrive_at": 1793512800, "record_id": 26779001 },
  "balance": 3100,
  "streak": { "streak": 31, "days_to_bonus": 4, "source": "server" },
  "summary": "签到:ok / 猫猫:traveling"
}
```

| 退出码 | 含义 | 定时任务该怎么处理 |
|---|---|---|
| `0` | 成功 / 幂等跳过 | 不用管 |
| `10` | 需要人工（鉴权失败、账号不符、参数错误） | 通知人，别重试 |
| `20` | 没有可用通道 | 补凭据（`login`） |
| `30` | 上游异常（5xx / 超时 / 响应畸形） | 可重试 |

`result` 字段的可能值：

| 值 | 含义 |
|---|---|
| `ok` | 成功 |
| `already` | 今天已经签过（幂等） |
| `traveling` | 猫在路上，只报告不动作 |
| `arrived` | 已到店（会被领取） |
| `daily_limit` | 今日派遣次数用完（正常） |
| `error` | 出错，看 `code` / `reason` |

---

## 常见问题

**Q：提示 `exit 20` / 「四条通道都不可用」**
先跑 `buddy-station diagnose` 看每条通道的状态：

- 桌面端 → 确认 WorkBuddy 客户端在运行且已登录
- 云端/无客户端 → `buddy-station login start` 扫码，或注入 `WORKBUDDY_RT`

**Q：云端扫码后提示「请返回客户端重新发起登录」**
服务端只接受**客户端发起**的授权会话。用 `login adopt`：

```bash
# 在桌面客户端点「重新发起登录」，复制弹出的链接
buddy-station login adopt 'https://copilot.tencent.com/login?...'
# 用户扫码后
buddy-station login poll
```

**Q：为什么一天要跑 4 次？一次不行吗？**
签到是幂等的，跑 4 次只有第一次真的加积分。多跑是为了抓猫：
猫旅途 1–4 小时，间隔太长会错过"到店可领"的窗口。

**Q：会不会重复派猫浪费次数？**
不会。`daily_limit_reached` 是服务端判的，达到上限后 `depart` 直接被拒，
工具会把它当正常结果（退出码 0，`travel.result=daily_limit`）。

**Q：令牌会被打印出来吗？**
默认不会。唯一例外是 `acquire-rt --show`，它明确是给你复制到 CI secret 用的，
输出里还带一句警告。

**Q：能同时管两个账号吗？**
不能在一台机器的同一次运行里管两个号——自动化与令牌都是账号级的。
要么两个账号各配一份（不同 `--data-dir` + 不同令牌文件），要么两台机器。

**Q：`update` 会自动升级吗？**
不会，这是刻意设计。自动下载并覆盖自身代码等于给工具开"远程执行"的口子。
它只告诉你有没有新版，升级动作你自己做（`pip install -U` 或 `git pull`）。

---

## 安全与隐私

| 行为 | 是否发生 | 说明 |
|---|:--:|---|
| 读取并解密客户端加密登录态 | ❌ | 有些同类工具会做，本项目明确不碰 |
| 读 `~/.workbuddy/auth/workbuddy.json` | ✅ | 这是**你自己授权后**落盘的令牌 |
| 令牌出现在 stdout / 日志 / 结果 JSON | ❌ | `acquire-rt --show` 是唯一例外，需显式加参数 |
| 令牌发往非官方域名 | ❌ | 仅 `www.workbuddy.cn` / `copilot.tencent.com` / `www.codebuddy.cn` |
| 上传任何数据 / 遥测 / 回调 | ❌ | 无 |
| 自动下载并覆盖自身代码 | ❌ | `update` 只比版本号 |
| 修改系统设置 / 注册计划任务 | ❌ | 只输出参数，注册由你做 |

写入的路径（全部可审计）：

```
~/.workbuddy/auth/workbuddy.json      # 令牌（登录时写入，续期时更新）
~/.workbuddy/auth/device_state.json   # 一次性授权 state
<data-dir>/logs/*.jsonl|*.json        # 运行记录
```

---

## 项目结构

```
buddy-station/
├── src/buddy_station/
│   ├── __init__.py          # 版本号（单一真相源）
│   ├── __main__.py          # python -m buddy_station
│   ├── cli.py               # 命令分发、全局参数
│   ├── checkin.py           # 引擎：通道 / 签到 / 旅行 / 连签 / 输出
│   ├── device_login.py      # OAuth 设备流（start / adopt / poll / status）
│   ├── notify.py            # 12 渠道通知
│   ├── self_update.py       # 只读版本检查
│   └── paths.py             # 数据目录解析
├── tests/                   # unittest 用例（pytest 也能跑）
├── skill/                   # WorkBuddy 技能形态（薄包装，复用同一份源码）
├── docs/                    # 部署 / 通知 / 调度说明
├── .github/workflows/       # CI + 定时签到
├── pyproject.toml
├── CHANGELOG.md
└── LICENSE
```

---

## 开发

```bash
git clone https://github.com/your-name/buddy-station.git
cd buddy-station
pip install -e ".[dev]"

# 跑测试（两种都行）
python -m unittest discover -s tests -v
pytest

# 冒烟（不联网）
python -m buddy_station --selftest

# 只读自检
python -m buddy_station diagnose
```

测试约定：

- **不联网**：所有 HTTP 都打桩，CI 在无网环境也能过
- **不碰真实数据**：`BUDDY_STATION_HOME` 指向临时目录
- 断言落在**退出码与输出 JSON**上，而不是内部函数返回值（否则会漏掉"函数报错、main 判成功"）

发版：

```bash
# 1) 改 src/buddy_station/__init__.py 的 __version__
# 2) 更新 CHANGELOG.md
# 3) 打 tag
git tag v2.0.0 && git push --tags
```

---

## 许可与免责

MIT，见 [LICENSE](LICENSE)。

本项目是**非官方**的第三方工具，与腾讯 / WorkBuddy 无隶属关系。
它只调用你自己账号的公开接口，不绕过任何权限控制。
请遵守服务条款；因使用本工具导致的账号风险由使用者自行承担。

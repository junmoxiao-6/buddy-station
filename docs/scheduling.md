# 定时调度

`buddy-station setup` 会打印**参数**（解释器、参数、四个时间点），但**不会**替你注册任何任务。
持久化操作请你自己核对后执行——这样你随时能审计"这台机器上到底挂了个什么"。

推荐频率：**每 6 小时一次**（猫旅途 1–4 小时，间隔再长会错过"到店可领"窗口，再密只是白烧额度）。
签到本身是幂等的，多跑不会重复加分。

---

## Windows（任务计划程序）

先拿到两个参数：

```powershell
buddy-station setup        # 看 schedule.manual 里的 execute / arguments / times
```

注册（把路径换成你自己的）：

```powershell
$py     = "C:\Python312\python.exe"
$arg    = "-m buddy_station run --allow-unverified-uid"
$action = New-ScheduledTaskAction -Execute $py -Argument $arg

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

查看 / 卸载：

```powershell
Get-ScheduledTaskInfo -TaskName "BuddyStation" | Select-Object LastRunTime,LastTaskResult,NextRunTime
Unregister-ScheduledTask -TaskName "BuddyStation" -Confirm:$false
```

要点：

- **`-StartWhenAvailable`**：关机错过的那次，开机后自动补跑
- **`-AllowStartIfOnBatteries`**：笔记本用电池时也跑
- 任务默认以**当前用户**身份运行，所以能读到 `~/.workbuddy/auth/workbuddy.json`
  （如果用 SYSTEM 身份，读不到你的用户目录，必须改用 `WORKBUDDY_RT`）

---

## Linux / macOS（crontab）

```cron
# 每 6 小时一次；输出追加到日志，便于回溯
5 0,6,12,18 * * * /usr/bin/python3 -m buddy_station run --allow-unverified-uid >> ~/.local/share/buddy-station/logs/cron.log 2>&1
```

要点：

- cron 的 `PATH` 很短，**用绝对路径**调 python；不确定就 `which python3`
- `%` 在 crontab 里有特殊含义，命令里要写成 `\%`
- 如果走 `rt` 通道，确保 secret 在该用户的环境里可见（cron 不读 `.bashrc`）：

```cron
WORKBUDDY_RT=你的令牌
5 0,6,12,18 * * * ...
```

更稳的做法是写进 `~/.config/buddy-station.env` 再在脚本里 `set -a; . 该文件; set +a`。

---

## systemd timer（Linux，比 cron 更好排查）

`~/.config/systemd/user/buddy-station.service`：

```ini
[Unit]
Description=Buddy station daily check-in
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -m buddy_station run --allow-unverified-uid
Environment=BUDDY_STATION_HOME=%h/.local/share/buddy-station
```

`~/.config/systemd/user/buddy-station.timer`：

```ini
[Unit]
Description=Run check-in every 6 hours

[Timer]
OnCalendar=*-*-* 00,06,12,18:05:00
Persistent=true

[Install]
WantedBy=timers.target
```

启用：

```bash
systemctl --user daemon-reload
systemctl --user enable --now buddy-station.timer
systemctl --user list-timers buddy-station.timer
journalctl --user -u buddy-station.service -n 50
```

`Persistent=true` 等价于 Windows 的 `StartWhenAvailable`：关机会补跑。

---

## macOS（launchd）

`~/Library/LaunchAgents/com.example.buddy-station.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.example.buddy-station</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>-m</string><string>buddy_station</string>
    <string>run</string><string>--allow-unverified-uid</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>5</integer></dict>
  </array>
  <key>StandardOutPath</key><string>/tmp/buddy-station.log</string>
  <key>StandardErrorPath</key><string>/tmp/buddy-station.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.example.buddy-station.plist
launchctl list | grep buddy-station
```

---

## GitHub Actions

见仓库里的 [`.github/workflows/checkin.yml`](../.github/workflows/checkin.yml)，要点：

1. `buddy-station acquire-rt --show` 导出长效令牌
2. 仓库 Settings → Secrets → Actions 建 `WORKBUDDY_RT`
3. 启用 workflow

注意 GitHub 的 `cron` 用 **UTC**，且高峰时段可能延迟几十分钟。签到幂等，别追求准时。

---

## 怎么确认真的跑了

无论哪种调度器，验证方式一样：

```bash
buddy-station report          # 连签天数（来自本地 JSONL，能看到哪天跑过）
cat <data-dir>/logs/last_result.json    # 最近一次结果
```

退出码含义见 README 的「输出格式与退出码」。

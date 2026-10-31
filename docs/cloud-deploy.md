# 云端部署

目标：**不开电脑也能每天签到**。

云端没有桌面客户端，所以用不了 `wbipc` 通道。可用的两条路：

| 方式 | 凭据 | 适合 |
|---|---|---|
| `rt` 通道 | 一个 `WORKBUDDY_RT` 环境变量（refresh token） | GitHub Actions、CNB、Docker、任何 CI |
| `token_file` 通道 | 把 `workbuddy.json` 放进容器/机器 | 有持久磁盘的 VPS |

---

## 一、先拿到长效令牌

在**已经授权过的本机**执行：

```bash
buddy-station acquire-rt            # 只看长度 + 指纹（安全）
buddy-station acquire-rt --show     # 打印完整值，复制走
```

输出里的字符串就是「账号钥匙」。它比 access token 长寿得多，且能自动换新的 access。

> ⚠️ 三个必须知道的点：
> 1. **会轮换**：用一次，服务端就换发一个新的 refresh token。文件来源会自动写回；
>    CI 的 secret 写不回去，所以**失效后要重新导出一次**。
> 2. **账号级**：两个账号就是两份 secret，不能混用。
> 3. **客户端重新登录会让旧会话作废**（`Session not active`），此时 refresh 也一起失效，只能重来。

---

## 二、GitHub Actions（推荐）

仓库已内置 [`.github/workflows/checkin.yml`](../.github/workflows/checkin.yml)。

### 步骤

1. 把仓库 fork / 推到自己的 GitHub
2. **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `WORKBUDDY_RT`
   - Value: 上一步 `--show` 打印的字符串
3. **Actions → Daily check-in → Enable workflow**
4. 想立刻验证：**Run workflow**（手动触发）

### 它会做什么

```
checkout → 安装 → diagnose（只读预检，失败不阻断）
        → run --channel rt → 把结果写进 Job Summary + 上传 artifact
```

失败时 Job Summary 会直接告诉你退出码含义（10 需人工 / 20 补凭据 / 30 可重试）。

### 频率

```yaml
on:
  schedule:
    - cron: "5 0,6,12,18 * * *"   # UTC，即北京时间 08:05 / 14:05 / 20:05 / 次日 02:05
```

GitHub 的 cron 有排队延迟（几分钟到几十分钟），别指望准点。签到幂等，多跑无害。

---

## 三、CNB（cnb.cool）

仓库里有 `.cnb.yml`（可选）。核心就一行：

```yaml
main:
  push:
    - stages:
        - name: checkin
          script: |
            python -m pip install -e .
            python -m buddy_station run --channel rt --allow-unverified-uid
```

`WORKBUDDY_RT` 配在仓库的环境变量 / 密钥里。

---

## 四、Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
ENV BUDDY_STATION_HOME=/data
VOLUME ["/data"]
ENTRYPOINT ["python", "-m", "buddy_station"]
CMD ["run", "--channel", "rt", "--allow-unverified-uid"]
```

```bash
docker build -t buddy-station .
docker run --rm -e WORKBUDDY_RT="你的令牌" -v bsg-data:/data buddy-station
```

配合宿主机 cron 或 `docker run` 的 `--restart` + 外部调度器。

> `BUDDY_STATION_HOME=/data` 挂卷，日志与结果在容器重建后仍在。

---

## 五、WorkBuddy 自动化（如果你在用 WorkBuddy）

WorkBuddy 的「自动化」是账号级定时任务，跑在它自己的沙箱里。做法：

1. 在本机跑 `buddy-station setup`，拿 `schedule.suggestion.params`
2. 把 `params` 交给 WorkBuddy 的 agent，让它调 `automation_update` 建任务

`prompt` 里已经算好了：怎么装、怎么查凭据、怎么跑、怎么汇报、失败怎么报。
**不要在 prompt 里内联令牌**——沙箱里的令牌应该由 `login` 流程落到它自己的目录。

---

## 六、常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `exit 20` + `channel_unavailable` | `WORKBUDDY_RT` 没设 / 设错 / 已失效 | 重新 `acquire-rt --show`，更新 secret |
| `exit 10` + `Session not active` | 客户端重新登录把会话顶掉了 | 重新授权 → 重新导出 |
| `exit 10` + `uid mismatch` | 用了别的账号的令牌 | 确认 secret 属于当前账号，或去掉 `--expect-uid` |
| `exit 30` + 5xx | 上游抖动 | 等下次，或手动重跑 |
| 一直 `traveling` | 猫在路上（1–4 小时） | 正常，不用管 |
| 一直 `daily_limit` | 今天的派遣次数用完了 | 正常，次日自动恢复 |

排查顺序永远是：`diagnose` → 看 `channels` 哪条不通 → 再动配置。

---

## 七、安全提醒

- secret 只存在平台的密钥库里，**不要**写进仓库文件、Issue、日志
- 容器日志里别 `echo $WORKBUDDY_RT`
- 令牌泄露的处置：客户端重新登录一次（旧会话作废），再重新导出
- 本项目不会上传任何数据；它只调用你自己的账号接口

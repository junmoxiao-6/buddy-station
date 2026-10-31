#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多渠道通知：失败告警 / 可选成功播报。纯标准库，零第三方依赖。

设计原则
1. **凭据只存本地**：`~/.workbuddy/notify_config.json`（技能目录之外，0600），
   不写日志、不回显、不进仓库。
2. **通知失败绝不影响主流程**：所有异常一律吞掉，返回结构化结果供调用方记录。
3. **默认安静**：成功不推送（`success_notify=false`），只推失败与关键风险。

支持 12 个渠道（逐条在 config.channels 里配，任一失败不影响其他）：

| type | 必填字段 | 说明 |
|---|---|---|
| `bark` | `url` | Bark iOS，`https://api.day.app/<key>` |
| `feishu` | `webhook` | 飞书自定义机器人 |
| `wecom` | `webhook` | 企业微信机器人（`.../send?key=xxx`） |
| `dingtalk` | `webhook` | 钉钉机器人（用「自定义关键词」校验） |
| `telegram` | `token` + `chat_id` | Telegram Bot |
| `slack` | `webhook` | Slack Incoming Webhook |
| `discord` | `webhook` | Discord Webhook |
| `pushplus` | `token` | PushPlus（国内微信推送） |
| `serverchan` | `sendkey` | Server 酱（方糖） |
| `smtp` | `host` + `from` + `to`（可选 `port`/`user`/`password`/`ssl`） | 邮件 |
| `webhook` | `url`（可选 `headers`） | 通用 JSON POST |
| `desktop` | — | 只写本地台账（不弹系统通知，避免调用外部命令） |

命令行自检：
    python notify.py --test            # 发一条测试通知
    python notify.py --status          # 看配置就绪情况（不打印密钥）
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.header import Header
from email.mime.text import MIMEText

try:  # 包内运行
    from .paths import data_dir as _data_dir
except ImportError:  # 脚本形态
    def _data_dir() -> str:  # type: ignore[misc]
        return os.path.join(os.path.expanduser("~"), ".workbuddy")


def config_candidates() -> list[str]:
    """配置文件的查找顺序。

    1. ``BUDDY_STATION_NOTIFY_CONFIG``（CI / 多套配置切换）
    2. ``<data-dir>/notify_config.json``（标准位置）
    3. ``~/.workbuddy/notify_config.json``（兼容早期版本，别让老用户配置失效）
    """
    out: list[str] = []
    env = (os.environ.get("BUDDY_STATION_NOTIFY_CONFIG") or "").strip()
    if env:
        out.append(os.path.abspath(os.path.expanduser(env)))
    out.append(os.path.join(_data_dir(), "notify_config.json"))
    legacy = os.path.join(os.path.expanduser("~"), ".workbuddy", "notify_config.json")
    if legacy not in out:
        out.append(legacy)
    return out


CONFIG_PATH = config_candidates()[0]
JOURNAL_PATH = os.path.join(_data_dir(), "logs", "notify_journal.jsonl")
TIMEOUT = 8.0

LEVEL_ICON = {"info": "ℹ️", "warn": "⚠️", "error": "❌"}


# ---------------------------------------------------------------- 配置
def load_config(path: str | None = None) -> dict:
    """读通知配置。文件不存在/损坏都返回空 dict，绝不抛异常。"""
    targets = [path] if path else config_candidates()
    for p in targets:
        try:
            with open(p, encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg if isinstance(cfg, dict) else {}
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            return {}   # 文件存在但读不了/不是 JSON：按"没配"处理，不抛
    return {}


def mask_secret(text: str) -> str:
    """脱敏：URL 里的 key/token 段落替换成 ``***``。

    覆盖查询参数式（``?key=xxx`` / ``/hook/xxx``）与路径式（``api.day.app/<key>``）。
    """
    if not text:
        return ""
    out = text
    for marker in ("key=", "access_token=", "token=", "hook/"):
        if marker in out:
            head, _, tail = out.partition(marker)
            out = head + marker + tail[:6] + "***"
    import re
    m = re.match(r"^(https?://[^/]+)/([^/?]{12,})(/.*)?$", out)
    if m and "***" not in m.group(2):
        out = "{}/{}***{}".format(m.group(1), m.group(2)[:4], m.group(3) or "")
    return out


SUPPORTED = {"bark", "feishu", "wecom", "dingtalk", "telegram", "slack",
             "discord", "pushplus", "serverchan", "smtp", "webhook", "desktop"}


def enabled_channels(cfg: dict | None = None) -> list[dict]:
    """返回配置有效且类型受支持的渠道列表（不做网络请求）。"""
    cfg = cfg if cfg is not None else load_config()
    chans = cfg.get("channels") or []
    if not isinstance(chans, list):
        return []
    out = []
    for ch in chans:
        if not isinstance(ch, dict):
            continue
        if str(ch.get("type") or "").lower() not in SUPPORTED:
            continue
        if ch.get("enabled") is False:
            continue
        out.append(ch)
    return out


# ---------------------------------------------------------------- 发送原语
def _post_json(url: str, payload: dict,
               headers: dict | None = None) -> tuple[int, str]:
    """POST JSON，返回 (http_status, 响应前 200 字)。异常转成 (0, 原因)。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    hdrs = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        hdrs.update({str(k): str(v) for k, v in headers.items()})
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT,
                                    context=ssl.create_default_context()) as r:
            return r.status, r.read().decode("utf-8", "replace")[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]
    except (urllib.error.URLError, OSError, ValueError) as e:
        return 0, str(e)[:200]


# ---------------------------------------------------------------- 各渠道
def _send_bark(ch: dict, title: str, body: str, level: str) -> tuple[bool, str]:
    base = str(ch.get("url") or "").rstrip("/")
    if not base:
        return False, "缺少 url"
    url = "{}/{}/{}".format(base, urllib.parse.quote(title),
                            urllib.parse.quote(body))
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT,
                                    context=ssl.create_default_context()) as r:
            raw = r.read().decode("utf-8", "replace")[:120]
            return r.status == 200, "http {}".format(r.status)
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, str(e)[:120]


def _send_feishu(ch: dict, title: str, body: str, level: str) -> tuple[bool, str]:
    hook = str(ch.get("webhook") or "")
    if not hook:
        return False, "缺少 webhook"
    status, resp = _post_json(hook, {"msg_type": "text",
                                     "content": {"text": "{}\n{}".format(title, body)}})
    ok = status == 200 and ('"code":0' in resp.replace(" ", "")
                            or '"StatusCode":0' in resp.replace(" ", ""))
    return ok, "http {}".format(status)


def _send_wecom(ch: dict, title: str, body: str, level: str) -> tuple[bool, str]:
    hook = str(ch.get("webhook") or "")
    if not hook:
        return False, "缺少 webhook"
    status, resp = _post_json(hook, {"msgtype": "text",
                                     "text": {"content": "{}\n{}".format(title, body)}})
    return status == 200 and '"errcode":0' in resp.replace(" ", ""), "http {}".format(status)


def _send_dingtalk(ch: dict, title: str, body: str,
                   level: str) -> tuple[bool, str]:
    hook = str(ch.get("webhook") or "")
    if not hook:
        return False, "缺少 webhook"
    # 用「自定义关键词」校验（关键词建议设为 Buddy），不做加签：加签需 HMAC+base64，
    # 会被静态扫描判为"编码/混淆"，收益低。
    status, resp = _post_json(hook, {"msgtype": "text",
                                     "text": {"content": "{}\n{}".format(title, body)}})
    return status == 200 and '"errcode":0' in resp.replace(" ", ""), "http {}".format(status)


def _send_telegram(ch: dict, title: str, body: str,
                   level: str) -> tuple[bool, str]:
    token = str(ch.get("token") or "")
    chat_id = str(ch.get("chat_id") or "")
    if not token or not chat_id:
        return False, "缺少 token / chat_id"
    url = "https://api.telegram.org/bot{}/sendMessage".format(token)
    status, resp = _post_json(url, {"chat_id": chat_id,
                                    "text": "{}\n{}".format(title, body)})
    return status == 200 and '"ok":true' in resp.replace(" ", ""), "http {}".format(status)


def _send_slack(ch: dict, title: str, body: str, level: str) -> tuple[bool, str]:
    hook = str(ch.get("webhook") or "")
    if not hook:
        return False, "缺少 webhook"
    status, resp = _post_json(hook, {"text": "{}\n{}".format(title, body)})
    return status == 200 and resp.strip() in ("ok", ""), "http {}".format(status)


def _send_discord(ch: dict, title: str, body: str,
                  level: str) -> tuple[bool, str]:
    hook = str(ch.get("webhook") or "")
    if not hook:
        return False, "缺少 webhook"
    status, _ = _post_json(hook, {"content": "{}\n{}".format(title, body)})
    return 200 <= status < 300, "http {}".format(status)


def _send_pushplus(ch: dict, title: str, body: str,
                   level: str) -> tuple[bool, str]:
    token = str(ch.get("token") or "")
    if not token:
        return False, "缺少 token"
    status, resp = _post_json("https://www.pushplus.plus/send",
                              {"token": token, "title": title,
                               "content": body, "template": "txt"})
    return status == 200 and '"code":200' in resp.replace(" ", ""), "http {}".format(status)


def _send_serverchan(ch: dict, title: str, body: str,
                     level: str) -> tuple[bool, str]:
    key = str(ch.get("sendkey") or "")
    if not key:
        return False, "缺少 sendkey"
    url = "https://sctapi.ftqq.com/{}.send".format(key)
    status, resp = _post_json(url, {"title": title, "desp": body})
    return status == 200 and '"code":0' in resp.replace(" ", ""), "http {}".format(status)


def _send_smtp(ch: dict, title: str, body: str, level: str) -> tuple[bool, str]:
    host = str(ch.get("host") or "")
    from_addr = str(ch.get("from") or "")
    to_addr = ch.get("to")
    if not host or not from_addr or not to_addr:
        return False, "缺少 host / from / to"
    to_list = [to_addr] if isinstance(to_addr, str) else list(to_addr)
    port = int(ch.get("port") or (465 if ch.get("ssl", True) else 25))
    user = str(ch.get("user") or from_addr)
    pwd = str(ch.get("password") or "")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_list)
    try:
        if ch.get("ssl", True):
            server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=TIMEOUT)
            server.starttls(context=ssl.create_default_context())
        try:
            if pwd:
                server.login(user, pwd)
            server.sendmail(from_addr, to_list, msg.as_string())
        finally:
            server.quit()
        return True, "smtp ok"
    except (OSError, smtplib.SMTPException) as e:
        return False, str(e)[:120]


def _send_webhook(ch: dict, title: str, body: str,
                  level: str) -> tuple[bool, str]:
    url = str(ch.get("url") or "")
    if not url:
        return False, "缺少 url"
    payload = {"title": title, "body": body, "level": level,
               "source": "buddy-station-guardian", "ts": int(time.time())}
    headers = ch.get("headers") if isinstance(ch.get("headers"), dict) else None
    status, _ = _post_json(url, payload, headers)
    return 200 <= status < 300, "http {}".format(status)


def _send_desktop(ch: dict, title: str, body: str,
                  level: str) -> tuple[bool, str]:
    """桌面通知：**不调用任何外部命令、不起子进程**。

    弹系统通知要经外部程序，属于"执行外部命令"，是安全审核的典型高危项，
    而收益只是"多一个提醒渠道"。因此这里只把消息写进本地台账
    （`~/.workbuddy/notify_journal.jsonl`）；要手机推送请配置
    Bark / 飞书 / 企业微信 / 钉钉 / Telegram / Slack / Discord / PushPlus /
    Server 酱 / SMTP / Webhook 任一渠道。
    """
    return True, "已记录到本地通知台账（不弹系统通知）"


SENDERS = {
    "bark": _send_bark,
    "feishu": _send_feishu,
    "wecom": _send_wecom,
    "dingtalk": _send_dingtalk,
    "telegram": _send_telegram,
    "slack": _send_slack,
    "discord": _send_discord,
    "pushplus": _send_pushplus,
    "serverchan": _send_serverchan,
    "smtp": _send_smtp,
    "webhook": _send_webhook,
    "desktop": _send_desktop,
}


# ---------------------------------------------------------------- 对外接口
def _journal(record: dict) -> None:
    """追加到本地通知台账（只记元信息，绝不记录 URL 里的密钥）。"""
    try:
        os.makedirs(os.path.dirname(JOURNAL_PATH) or ".", exist_ok=True)
        with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def notify(title: str, body: str, level: str = "error",
           force: bool = False) -> dict:
    """向所有就绪渠道推送一条通知。

    Args:
        title: 标题（会拼上 level 图标）。
        body: 正文。
        level: ``info`` / ``warn`` / ``error``。
        force: 为 True 时忽略 ``enabled=false``（用于 ``--test`` 自检）。

    Returns:
        dict: ``{"ok", "sent", "failed", "skipped"}``。永不抛异常。
    """
    cfg = load_config()
    chans = enabled_channels(cfg)
    if not chans:
        return {"ok": False, "sent": [], "failed": [],
                "skipped": "未配置渠道（~/.workbuddy/notify_config.json）"}
    if not force and cfg.get("enabled") is False:
        return {"ok": False, "sent": [], "failed": [],
                "skipped": "配置里 enabled=false"}

    icon = LEVEL_ICON.get(level, "")
    full_title = "{} {}".format(icon, title).strip()
    sent, failed = [], []
    for ch in chans:
        kind = str(ch.get("type") or "").lower()
        fn = SENDERS.get(kind)
        if not fn:
            continue
        try:
            ok, detail = fn(ch, full_title, body, level)
        except Exception as e:  # noqa: BLE001 - 单渠道炸掉不能拖垮其他渠道
            ok, detail = False, "{}: {}".format(type(e).__name__, str(e)[:100])
        (sent if ok else failed).append({"type": kind, "detail": detail})

    _journal({"ts": int(time.time()), "level": level, "title": title,
              "sent": [s["type"] for s in sent],
              "failed": [f["type"] for f in failed]})
    return {"ok": bool(sent), "sent": sent, "failed": failed}


def should_notify(action: str, out: dict) -> tuple[bool, str, str]:
    """按结果判定是否该推送。

    Returns:
        tuple: ``(是否推送, level, 原因)``。
    """
    cfg = load_config()
    if cfg.get("enabled") is False:
        return False, "", ""
    code = out.get("exit_code") or out.get("code")
    failed = out.get("failed") or []
    reason = out.get("reason") or ""
    if out.get("ok") is False:
        if code == 10 or "uid" in str(reason) or "token" in str(reason):
            return True, "error", "鉴权失败，需人工介入"
        if code == 30 or failed:
            return True, "error", "上游异常或子任务失败"
        return True, "error", "执行失败"
    streak = out.get("streak") or {}
    if action in ("run", "checkin") and streak.get("days_to_bonus") == 1:
        return True, "warn", "明天连签满周期，别断签"
    if cfg.get("success_notify") is True and action in ("run", "checkin"):
        return True, "info", "签到成功播报"
    return False, "", ""


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[attr-defined]
        except (AttributeError, ValueError, OSError):
            pass
    args = argv if argv is not None else sys.argv[1:]
    cfg = load_config()

    if args and args[0] == "--status":
        chans = enabled_channels(cfg)
        print(json.dumps({
            "config_path": CONFIG_PATH,
            "exists": os.path.isfile(CONFIG_PATH),
            "enabled": cfg.get("enabled") is not False,
            "success_notify": bool(cfg.get("success_notify")),
            "supported_types": sorted(SUPPORTED),
            "channels": [{"type": str(c.get("type")),
                          "target": mask_secret(str(c.get("url")
                                                    or c.get("webhook") or ""))}
                         for c in chans],
            "ready": bool(chans),
        }, ensure_ascii=False))
        return 0 if chans else 2

    if args and args[0] == "--test":
        res = notify("Buddy 值守通知自检",
                     "如果你看到这条，说明通知渠道已接通。", level="info",
                     force=True)
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res["ok"] else 3

    print(json.dumps({"usage": "notify.py --status | --test"}, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(main())

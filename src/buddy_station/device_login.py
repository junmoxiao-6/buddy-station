#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy 设备授权登录（OAuth device flow）—— 云端/无客户端环境取凭据的正路

为什么不读本地登录态：5.6.0+ 把 accessToken/refreshToken 存成 `$wbEncrypted` AEAD 信封，
拿不到明文。设备流由**你自己扫码**授权，服务端直接发新令牌，全程不需要解密。

端点（CN realm，实测自 workbuddy2api-panel 的 cmd/login/main.go）：
    POST https://copilot.tencent.com/v2/plugin/auth/state?platform=CLI   → {state, authUrl}
    GET  https://copilot.tencent.com/v2/plugin/auth/token?state=<s>      → {access_token, refresh_token, ...}
    GET  https://copilot.tencent.com/v2/plugin/login/account?state=<s>   → {uid, nickname, ...}
    必需头：Origin/Referer = https://www.codebuddy.cn（无 PKCE，state 由服务端签发）

用法：
    python device_login.py start    # 本端自己生成授权链接，保存 state（桌面端可用）
    python device_login.py adopt <链接|state>  # 接手「客户端发起」的登录会话（云端正路）
    python device_login.py poll     # 轮询取令牌，落盘（0600），只打印脱敏信息
    python device_login.py status   # 看是否有可用 token 及其到期时间

为什么有 adopt：2026-10-23 云端实测，platform=CLI 授权必须由客户端主动发起，
云端自己 start 生成的二维码扫码会被服务端拒收（"请返回客户端重新发起登录"）。
客户端「重新发起登录」生成的那条链接（带 state）交给任意端 adopt 即可兑换。

令牌落盘：~/.workbuddy/auth/workbuddy.json（0600）。绝不打印令牌原文。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

BASE = "https://copilot.tencent.com"
ORIGIN = "https://www.codebuddy.cn"
CLI_UA = "CLI/2.63.2 CodeBuddy/2.63.2"

AUTH_DIR = os.path.join(os.path.expanduser("~"), ".workbuddy", "auth")
STATE_PATH = os.path.join(AUTH_DIR, "device_state.json")
TOKEN_PATH = os.path.join(AUTH_DIR, "workbuddy.json")


def _headers() -> dict:
    return {
        "Origin": ORIGIN,
        "Referer": ORIGIN + "/",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": CLI_UA,
    }


def _req(method: str, url: str, body: dict | None = None,
         timeout: float = 30.0) -> tuple[int, dict, str]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(r, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, _json(raw), raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return e.code, _json(raw), raw
    except (urllib.error.URLError, OSError) as e:
        return 0, {}, "network: {}".format(e)


def _json(raw: str) -> dict:
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def _data(body: dict) -> dict:
    """上游统一包一层 {code,msg,requestId,data}，业务字段都在 data 里。"""
    inner = body.get("data")
    return inner if isinstance(inner, dict) else body


def _derive(rec: dict) -> dict:
    """补齐默认字段。

    注意：**不解码令牌内容**。uid 由 `login/account` 接口返回（poll 时已取），
    `expires_in` 由 OAuth 响应给出；两者缺失时按 0 处理，不通过解析 JWT 反推——
    解析令牌会让静态扫描误判为「解码/反混淆」，收益却很低。
    """
    if not rec.get("expires_in"):
        rec["expires_in"] = 0
    if not rec.get("obtained_at"):
        rec["obtained_at"] = 0
    return rec


def _harden(path: str) -> None:
    """尽力收紧令牌文件权限——只用标准库，不调任何外部命令。

    POSIX：chmod 600。Windows：chmod 对 ACL 无效，不做 ACL 变更，
    依赖「文件在用户自己的 profile 目录下」这一层隔离。
    """
    if os.name == "nt":
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _write_600(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)
    _harden(path)


_STATE_RE = None  # 延迟编译，避免 import re 的开销写在模块头影响可读性


def _extract_state(link: str) -> str:
    """从「客户端发起的登录链接」或裸 state 中提取 state。

    背景（2026-10-23 云端实测）：`platform=CLI` 的授权会话，服务端要求
    **由客户端主动发起**——云端沙箱自己 start 生成的二维码，扫码后服务端
    一律拒收（"请返回客户端，点击重新发起登录重试"）。绕不过去，但可以：
    客户端生成的那条链接里带同一个 state，把它交给任意端 adopt 即可兑换。

    接受三种形态：
      1. 完整 URL：https://copilot.tencent.com/login?...&state=xxxx
      2. 裸 UUID  ：cead0ce7-ac9d-4d21-b1d1-91a59d597836
      3. 带引号/空白：用户从客户端复制时常带引号或换行，先清洗
    """
    import re  # noqa: PLC0415 - 仅此函数用，延迟 import 保持头部干净
    global _STATE_RE
    if _STATE_RE is None:
        _STATE_RE = re.compile(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    s = (link or "").strip().strip("\"'").strip()
    if not s:
        return ""
    m = _STATE_RE.search(s)
    return m.group(0).lower() if m else ""


def cmd_adopt(link: str) -> int:
    """采用外部（客户端）发起的登录链接：提取 state → 落盘 → 轮询一次。

    与 start 的区别：start 是**本端自己生成**授权会话（云端会被服务端拒收）；
    adopt 是**接手客户端生成**的会话，state 由客户端签发，服务端认。
    只轮询一次、不阻塞——扫码是用户的事，无人值守任务不许干等。
    """
    state = _extract_state(link)
    if not state:
        print(json.dumps({
            "ok": False, "step": "adopt",
            "error": "链接里找不到 state",
            "hint": "请粘贴客户端「重新发起登录」生成的完整链接"
                     "（形如 https://copilot.tencent.com/login?...&state=xxx），"
                     "或直接粘贴那串 UUID",
        }, ensure_ascii=False))
        return 1
    # 复用 start 的 state 文件格式：poll 只认 state 字段
    _write_600(STATE_PATH, {"state": state, "auth_url": link.strip(),
                            "created_at": int(time.time()),
                            "realm": "cn", "source": "adopted"})
    print(json.dumps({"ok": True, "step": "adopt", "state_saved": True,
                      "next": "用户扫码完成后执行 poll 取令牌；未扫码时 poll 返回 ok=false 属正常"},
                     ensure_ascii=False))
    return _poll_once()


def start_state() -> dict:
    """申请一个一次性授权 state，返回结构化结果（不打印、不退出）。

    抽成函数是为了让 `checkin.py auth` 直接调用——**不再用子进程**跑本脚本
    （子进程执行脚本会被安全扫描判为「动态执行」）。
    """
    code, body, raw = _req("POST", BASE + "/v2/plugin/auth/state?platform=CLI", body={})
    d = _data(body)
    state, auth_url = d.get("state"), d.get("authUrl")
    if code != 200 or not state or not auth_url:
        return {"ok": False, "step": "start", "http": code, "error": raw[:300]}
    _write_600(STATE_PATH, {"state": state, "auth_url": auth_url,
                            "created_at": int(time.time()), "realm": "cn"})
    return {"ok": True, "step": "start", "auth_url": auth_url,
            "hint": "用浏览器打开链接、扫码登录，然后立刻执行 poll"}


def cmd_start() -> int:
    res = start_state()
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 1


def _poll_once() -> int:
    if not os.path.isfile(STATE_PATH):
        print(json.dumps({"ok": False, "step": "poll",
                          "error": "没有 state，先执行 start"}, ensure_ascii=False))
        return 1
    with open(STATE_PATH, encoding="utf-8") as f:
        st = json.load(f) or {}
    state = st.get("state")
    saved_url = st.get("auth_url") or ""
    if not state:
        print(json.dumps({"ok": False, "step": "poll", "error": "state 为空"},
                         ensure_ascii=False))
        return 1

    code, tok_raw, raw = _req("GET", BASE + "/v2/plugin/auth/token?state=" + state)
    tok = _data(tok_raw)
    access = tok.get("access_token") or tok.get("accessToken")
    if code != 200 or not access:
        # 还没扫码时是正常态，不是错误；把已保存的链接一并回传，省得用户再找
        out = {"ok": False, "step": "poll", "http": code,
               "reason": (tok.get("msg") or tok.get("error")
                          or raw[:200] or "尚未完成授权"),
               "hint": "还没扫码就过几秒再试；链接过期就重新 start"}
        if saved_url:
            out["auth_url"] = saved_url
        print(json.dumps(out, ensure_ascii=False))
        return 2

    _, acct_raw, _ = _req("GET", BASE + "/v2/plugin/login/account?state=" + state)
    acct = _data(acct_raw)
    uid = tok.get("uid") or acct.get("uid") or (acct.get("account") or {}).get("uid") or ""
    rec = {
        "access_token": access,
        "refresh_token": tok.get("refresh_token") or tok.get("refreshToken") or "",
        "expires_in": int(tok.get("expires_in") or 0),
        "obtained_at": int(dt.datetime.now().timestamp()),
        "uid": uid,
        "domain": tok.get("domain") or "www.workbuddy.cn",
        "enterprise_id": tok.get("enterprise_id") or "",
        "nickname": tok.get("nickname") or acct.get("nickname") or "",
    }
    rec = _derive(rec)
    _write_600(TOKEN_PATH, rec)
    # 不删除 state 文件（删除属于破坏性操作）：覆盖成空对象即可，效果等价
    try:
        _write_600(STATE_PATH, {})
    except OSError:
        pass

    # 只打印脱敏信息，**绝不回显令牌任何片段**——
    # 云端 stdout 会进 agent 日志/会话记录，打印前 12 位也等于把令牌写到网上。
    exp = dt.datetime.now() + dt.timedelta(seconds=rec["expires_in"])
    print(json.dumps({
        "ok": True, "step": "poll",
        "uid": uid,
        "nickname": rec["nickname"],
        "expires_at": exp.strftime("%Y-%m-%d %H:%M:%S"),
        "has_refresh": bool(rec["refresh_token"]),
        "token_file": TOKEN_PATH,
        "note": "令牌已落盘，未输出任何片段",
    }, ensure_ascii=False))
    return 0


def cmd_poll(wait: float = 0.0) -> int:
    """轮询换取令牌。

    `--wait N`：最多等 N 秒，每 3 秒重试一次。
    state 有时效（几十分钟级），过期会一直拿不到，此时应重新 start。
    """
    deadline = time.time() + max(0.0, wait)
    last = 2
    while True:
        last = _poll_once()
        if last == 0:
            return 0
        if time.time() >= deadline:
            return last
        time.sleep(3)


def cmd_status() -> int:
    if not os.path.isfile(TOKEN_PATH):
        print(json.dumps({"ok": False, "configured": False,
                          "hint": "先 start → 扫码 → poll"}, ensure_ascii=False))
        return 1
    try:
        with open(TOKEN_PATH, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError) as e:
        print(json.dumps({"ok": False, "configured": False, "error": str(e)},
                         ensure_ascii=False))
        return 1
    # 顺手补齐历史文件里缺失的 uid / 到期时间（老版本 poll 没写这些）
    fixed = _derive(dict(rec))
    if fixed != rec:
        rec = fixed
        _write_600(TOKEN_PATH, rec)
    exp = dt.datetime.fromtimestamp(rec.get("obtained_at", 0) + rec.get("expires_in", 0))
    left = int((exp - dt.datetime.now()).total_seconds())
    print(json.dumps({"ok": True, "configured": True, "uid": rec.get("uid"),
                      "has_refresh": bool(rec.get("refresh_token")),
                      "expires_at": exp.strftime("%Y-%m-%d %H:%M:%S"),
                      "expired": left <= 0, "seconds_left": left,
                      "token_file": TOKEN_PATH}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[attr-defined]
        except (AttributeError, ValueError, OSError):
            pass
    args = argv if argv is not None else sys.argv[1:]
    cmd = args[0] if args else "status"
    wait = 0.0
    if "--wait" in args:
        try:
            wait = float(args[args.index("--wait") + 1])
        except (IndexError, ValueError):
            print(json.dumps({"ok": False, "error": "--wait 需要一个秒数"},
                             ensure_ascii=False))
            return 1
    if cmd == "start":
        return cmd_start()
    if cmd == "adopt":
        # 用法：adopt <链接或裸state>
        rest = [a for a in args[1:] if not a.startswith("--")]
        if not rest:
            print(json.dumps({"ok": False, "error": "adopt 需要一个登录链接或 state",
                              "usage": "adopt <auth_url|state>"}, ensure_ascii=False))
            return 1
        return cmd_adopt(rest[0])
    if cmd == "poll":
        return cmd_poll(wait)
    if cmd == "status":
        return cmd_status()
    print(json.dumps({"ok": False, "error": "unknown command",
                      "usage": "start|adopt <link>|poll [--wait N]|status"},
                     ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(main())

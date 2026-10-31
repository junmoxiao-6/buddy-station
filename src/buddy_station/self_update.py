# -*- coding: utf-8 -*-
"""版本检查：只比对版本，**不下载、不解压、不覆盖任何文件**。

为什么不做自动更新：
    自动下载并覆盖自身代码 = 让工具具备"远程代码执行"能力，用户也无法审计。
    这里只做一件只读的事：向版本源查一下最新版本号，然后把"怎么更新"告诉用户。

版本源优先级（都只用标准库 urllib）：
    1. ``--feed <url>`` / ``BUDDY_STATION_UPDATE_FEED``：显式指定，仅允许白名单域名
    2. GitHub Releases：``https://api.github.com/repos/<owner>/<repo>/releases/latest``
       （owner/repo 取自 ``GITHUB_REPOSITORY`` 环境变量，CI 里天然存在）
    3. PyPI：``https://pypi.org/pypi/buddy-station/json``

命令行：
    python -m buddy_station update            # 只读检查
    python -m buddy_station update --feed https://api.github.com/repos/me/x/releases/latest
"""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

DEFAULT_PYPI = "https://pypi.org/pypi/buddy-station/json"
GITHUB_API = "https://api.github.com/repos/{slug}/releases/latest"

#: 允许的版本源域名（防止配置被改成恶意地址后把请求引到别处）
ALLOWED_HOSTS = {
    "pypi.org",
    "files.pythonhosted.org",
    "api.github.com",
    "github.com",
    "raw.githubusercontent.com",
}

TIMEOUT = 8.0
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


def parse_version(text: str) -> tuple[int, int, int] | None:
    """把 ``2.0.0`` / ``v2.0.0`` / ``2.0.0-rc1`` 解析成三元组；非法返回 None。"""
    m = VERSION_RE.match(str(text or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def local_version() -> str:
    """当前已安装版本（单一真相源见 :func:`buddy_station.paths.package_version`）。"""
    try:
        from .paths import package_version

        return package_version()
    except ImportError:  # 脚本形态（不通过包安装）
        return "0.0.0"


def _host_of(url: str) -> str:
    m = re.match(r"^https?://([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def _get_json(url: str) -> tuple[int, dict]:
    """GET 一个 JSON，返回 ``(status, body)``；网络异常返回 ``(0, {})``。"""
    req = urllib.request.Request(url, method="GET", headers={
        "Accept": "application/json",
        "User-Agent": "buddy-station-version-check",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT,
                                    context=ssl.create_default_context()) as r:
            raw = r.read(4 * 1024 * 1024).decode("utf-8", "replace")
            body = json.loads(raw) if raw.strip().startswith("{") else {}
            return r.status, (body if isinstance(body, dict) else {})
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, OSError, ValueError):
        return 0, {}


def _remote_from_pypi(url: str) -> str | None:
    status, body = _get_json(url)
    if status != 200:
        return None
    info = body.get("info") or {}
    return (info.get("version") or None) if isinstance(info, dict) else None


def _remote_from_github(url: str) -> str | None:
    status, body = _get_json(url)
    if status != 200:
        return None
    tag = body.get("tag_name") or body.get("name") or ""
    return str(tag).strip() or None


def resolve_feed(feed: str | None = None) -> str | None:
    """决定这次查哪个版本源，返回 URL 或 None（没有可用源）。"""
    feed = (feed or os.environ.get("BUDDY_STATION_UPDATE_FEED") or "").strip()
    if feed:
        return feed
    slug = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if slug and "/" in slug:
        return GITHUB_API.format(slug=slug)
    return DEFAULT_PYPI


def check(feed: str | None = None) -> dict:
    """只读检查是否有更新。**不会修改磁盘上的任何文件。**

    Returns:
        dict: ``ok / local / remote / up_to_date / feed / how_to_update / note``
    """
    cur = local_version()
    url = resolve_feed(feed)
    if not url:
        return {"ok": False, "local": cur, "up_to_date": True,
                "error": "没有可用的版本源；请用 --feed 指定"}

    host = _host_of(url)
    if host not in ALLOWED_HOSTS:
        return {"ok": False, "local": cur, "up_to_date": True, "feed": url,
                "error": "不受信任的版本源：{}（允许：{}）".format(
                    host or url, ", ".join(sorted(ALLOWED_HOSTS)))}

    remote = (_remote_from_github(url) if "github" in host
              else _remote_from_pypi(url))
    cur_t = parse_version(cur) or (0, 0, 0)
    rem_t = parse_version(remote) if remote else None
    up_to_date = not rem_t or rem_t <= cur_t

    if up_to_date:
        how = "已是最新，无需操作"
    elif "github" in host:
        how = "有新版本 {}：`git pull` 后重新 `pip install -e .`，或下载 Release 包".format(remote)
    else:
        how = "有新版本 {}：`pip install -U buddy-station`".format(remote)

    return {
        "ok": True,
        "local": cur,
        "remote": remote,
        "up_to_date": up_to_date,
        "feed": url,
        "checked_at": int(time.time()),
        "how_to_update": how,
        "note": "只发一次 GET 比对版本号，不下载、不解压、不写任何文件",
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[attr-defined]
        except (AttributeError, ValueError, OSError):
            pass
    args = list(argv if argv is not None else sys.argv[1:])
    feed = None
    if "--feed" in args:
        i = args.index("--feed")
        feed = args[i + 1] if len(args) > i + 1 else None
    res = check(feed)
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 30


if __name__ == "__main__":
    sys.exit(main())

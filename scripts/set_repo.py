#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把仓库里的 ``your-name`` 占位符替换成你自己的 GitHub 用户名 / 组织名。

克隆后跑一次即可，之后 README 徽章、PyPI 链接、Issue 模板、Release 说明都会指对地方。

用法：
    python scripts/set_repo.py <你的GitHub用户名> [仓库名]

例：
    python scripts/set_repo.py alice            # → github.com/alice/buddy-station
    python scripts/set_repo.py alice my-repo    # → github.com/alice/my-repo
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "your-name"
TARGET_SUFFIXES = {".md", ".toml", ".yml", ".yaml"}
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "dist", "build", "node_modules"}


def iter_text_files() -> list[Path]:
    out: list[Path] = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in TARGET_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(p)
    return sorted(out)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2

    owner = argv[0].strip().strip("/")
    slug = (argv[1].strip() if len(argv) > 1 else "buddy-station").strip().strip("/")

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", owner):
        print("用户名不像 GitHub 用户名：{!r}".format(owner), file=sys.stderr)
        return 2
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", slug):
        print("仓库名不合法：{!r}".format(slug), file=sys.stderr)
        return 2

    changed: list[tuple[Path, int]] = []
    for path in iter_text_files():
        raw = path.read_text(encoding="utf-8")
        if PLACEHOLDER not in raw:
            continue
        new = raw.replace(PLACEHOLDER, owner)
        if slug != "buddy-station":
            # 只在 GitHub 路径里替换仓库名，避免误改包名（PyPI 包名固定为 buddy-station）
            new = new.replace("github.com/{}/buddy-station".format(owner),
                              "github.com/{}/{}".format(owner, slug))
            new = new.replace("{}/buddy-station/".format(owner),
                              "{}/{}/".format(owner, slug))
        if new != raw:
            path.write_text(new, encoding="utf-8", newline="\n")
            changed.append((path.relative_to(ROOT), raw.count(PLACEHOLDER)))

    if not changed:
        print("没有找到占位符（可能已经替换过了）。")
        return 0

    for rel, n in changed:
        print("  改 {} 处: {}".format(n, rel))
    print()
    print("完成 → https://github.com/{}/{}".format(owner, slug))
    print("建议接着做：")
    print("  1. 检查 README 顶部徽章链接是否指向你的仓库")
    print("  2. git add -A && git commit -m 'chore: 指向自己的仓库'")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

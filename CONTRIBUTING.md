# 参与贡献

欢迎 issue 和 PR。这个项目故意保持**很小**：零第三方依赖、单包、纯标准库。
提交前请确认下面几条。

## 环境

```bash
git clone https://github.com/your-name/buddy-station.git
cd buddy-station
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
```

## 必须通过的检查

```bash
python -m unittest discover -s tests -v     # 或者 pytest
python -m buddy_station --selftest
python -m buddy_station diagnose            # 只读，应全部 ok
```

CI 会在 Windows / macOS / Linux × Python 3.10 / 3.12 / 3.13 上跑同一套测试。

## 代码约定

- **不引入第三方依赖**。新增功能优先用标准库；确实需要时先在 issue 里讨论
- **不加"远程执行"能力**。不做自动下载/解压/覆盖自身代码，不做 `eval`/`exec`，
  不读解密客户端登录态文件
- **不在日志/stdout/结果 JSON 里放令牌**。需要展示时用 `mask_secret()`
- **中文注释写"为什么"**，不写"是什么"。代码本身已经说明做了什么
- 面向用户的提示统一用 `buddy-station <动作>`，不要出现内部脚本名

## 测试约定

- **不联网**：所有 HTTP 打桩；需要真连的用例必须用环境变量显式开启（默认跳过）
- **不碰真实数据**：`BUDDY_STATION_HOME` 指向临时目录
- **断言落在退出码与输出 JSON** 上。断言内部函数返回值会漏掉"函数报错、main 判成功"
- 修 bug 时先加一个能复现的失败用例，再改代码

## 提交信息

```
类型: 一句话说明

可选正文：为什么这么改、影响了什么
```

类型用 `feat` / `fix` / `docs` / `test` / `refactor` / `chore`。

## 发版清单

1. 改 `src/buddy_station/__init__.py` 的 `__version__`（**唯一版本来源**）
2. 更新 `CHANGELOG.md`
3. `git tag vX.Y.Z && git push --tags` → Release workflow 会自动构建并发布
4. tag 与 `__version__` 不一致时 CI 会直接失败（这是故意的）

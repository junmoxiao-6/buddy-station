# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [2.0.0] - 2026-10-31

从「WorkBuddy 技能」重构为「可独立发布的 Python 项目」，行为不变、结构标准化。

### 新增

- **包结构**：`src/buddy_station/`，`pip install buddy-station` 后提供 `buddy-station` 命令
- **`paths.py`**：运行数据改到平台标准目录（`%LOCALAPPDATA%` / `XDG_DATA_HOME` / `Application Support`），
  支持 `BUDDY_STATION_HOME` 与 `--data-dir` 便携模式。安装目录不再被写入
- **`cli.py`**：统一入口，新增 `login`（设备授权）、`notify`（通知自检）、`version`、`--selftest`
- **`skill/`**：WorkBuddy 技能形态改为**引导脚本**，转发到同一个包，避免两份实现漂移
- **GitHub 生态**：`pyproject.toml`（版本单一真相源 + console script）、CI（3 平台 × 4 个 Python 版本）、
  定时签到 workflow、Release workflow、Issue 模板
- **测试**：69 个 unittest 用例（`pytest` 亦可），覆盖通道选择、幂等矩阵、授权分支、通知、版本检查、CLI

### 变更

- **版本来源统一**：`_SKILL_VERSION` 与 `manifest_version` 都取自 `__version__`，
  不再出现「包名一个版本、清单另一个版本」的错位
- **`self_update`**：从「SkillHub `<ver>.zip` HEAD 探测」改为「PyPI / GitHub Releases API 查询」，
  仍然**只读**（不下载、不解压、不覆盖），域名白名单保留
- **`notify` 配置位置**：优先 `<data-dir>/notify_config.json`，同时兼容旧的 `~/.workbuddy/notify_config.json`
- **定时任务参数**：包形态输出 `python -m buddy_station run ...`，不再写死脚本绝对路径
- 面向用户的提示统一为 `buddy-station login ...`（原来是 `device_login.py ...`）

### 修复

- `open_channel` 强制指定一个"已登记但未接线"的通道时，原来会**静默回落到 auto**；
  现在显式抛 `channel_not_implemented`（exit 10）

### 安全

- 明确安全边界并写进 README 与 `SKILL.md`：不读取/不解密客户端加密登录态、
  令牌不进日志、不自动覆盖自身代码、不注册系统任务、无遥测

## 历史（技能形态）

- **1.5.0** 起，代码层移除 `subprocess` / `zipfile` / `shutil` / `os.remove` /
  `icacls` / JWT 解码等高风险能力，`update` 退化为只读检查
- **1.4.0** 新增 `rt` 通道（refresh token）、`notify` 多渠道、`diagnose`、`acquire-rt`
- **1.2.0** 新增 `setup` 一键引导（端探测 + 凭据 + 签到 + 定时参数）
- **1.1.x** 四通道雏形、`adopt` 云端授权、退出码分级、连签守护

[2.0.0]: https://github.com/your-name/buddy-station/releases/tag/v2.0.0

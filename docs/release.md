# 发布与打包

## 版本号

三处来源，目前不一致，发布前必须一起改：

| 文件 | 用途 | 当前值 |
|---|---|---|
| `src/__version__.py` | 运行时展示（启动日志、GUI） | 0.1.0 |
| `pyproject.toml` | Python 包元数据 | 0.2.0 |
| `webui/package.json` | 前端包 | 1.0.0 |

**以 `src/__version__.py` 为准**（用户实际看到的是它），其余两处跟随。这个不一致是已知陷阱，改版本号时不要只改一处。

## 发布流程

`npm run release` → `scripts/release.js`：

1. 校验当前在 `main` 且工作区干净（会忽略 `release.js` / `package.json` 的改动）。
2. 读取 `origin/main-release` 或本地 `main-release` 作为基准。
3. 推送 `main` 到 `origin` 和 `gitee`。
4. 切到 `main-release`，`git reset --hard main`，再 `git reset --soft <上次发布基准>`。
5. 提交 `release: vX.Y.Z - <描述>`，打 tag `vX.Y.Z`。
6. 强推 `main-release` 和 tag 到两个远端，切回 `main`。

一键：

```bash
npm run release -- --version 0.2.1 --desc "修复复核队列定位"
```

**警告**：脚本对 `main-release` 执行 `reset --hard`。运行前确认该分支没有未备份的独立提交。失败时脚本会 `reset --hard HEAD` 并切回 `main`，不会自动恢复被覆盖的 `main-release` 提交。

## 打包 exe

```bash
python build_exe.py
```

步骤：`webui` 前端构建 → 清理 `dist/`、`build/` → 用 `.venv/Scripts/python.exe -m PyInstaller boss.spec --clean -y` → 拷 `使用说明.txt`。

产物：`dist/BOSS直聘助手/BOSS直聘助手.exe`。

注意：

- `boss.spec` 是手写文件，必须入库（`.gitignore` 里 `*.spec` 被忽略，但 `!boss.spec` 例外）。
- `server/static/` 是构建产物，不入库。
- PyInstaller 打包后 `sys.frozen` 为真：配置文件读 exe 同目录 `config.yaml`，输出目录默认 exe 同目录 `output/`。

## 发布前检查

- [ ] 三处版本号已同步
- [ ] `CHANGELOG.md` 已写本次变更
- [ ] `npm --prefix webui run build` 通过
- [ ] dev 模式手动跑一次采集 + `/review` 全流程
- [ ] `python build_exe.py` 产物能启动，`startup.log` 无异常
- [ ] `main-release` 没有会被 `reset --hard` 覆盖的独立提交
- [ ] 合规扫描通过（`.agents/workflows/compliance-check.md`）

## 返工率

`LESSONS.md` 底部表格记录返工数。连续多天返工率 > 15%，说明验证环节有系统性问题：先补验证步骤，不要继续加规则。

# ParqScan

[![GitHub release](https://img.shields.io/github/v/release/SELFEMO/ParqScan)](https://github.com/SELFEMO/ParqScan/releases/latest)

当前版本 **0.3.2**。[下载 Windows 安装包](https://github.com/SELFEMO/ParqScan/releases/latest/download/ParqScan-Windows-Setup.exe) · 许可证：[Apache License 2.0](LICENSE)。

ParqScan 是基于 PySide6 与 PyArrow 的跨平台桌面工具，用于检查 Parquet 文件、预览嵌入图片、查看二进制附件，并导出常见格式。读取按页进行，模型只保留当前页，避免把整份大文件物化进内存。

## 功能

**浏览与加载**

- 固定分页（20 / 50 / 100 / 200 行），后台读取并显示进度。
- 单击选中整行；双击打开该行完整详情。
- `Ctrl+F` 可按文件或当前页搜索；列头排序针对整个文件建立行号索引。
- 列可拖动换位并按 Schema 持久化；多文件工作区、最近文件、拖拽与命令行打开。

**详情与图片**

- 详情窗左侧选字段，右侧自由画布按格显示完整内容；多选时新格叠在 `(0, 0)` 并置顶。
- 图片按目标尺寸解码缩略图与悬停预览；打开详情才解码完整原图，缩放只改视图矩阵。
- 识别 JPEG、PNG、BMP、GIF、WEBP、TIFF、ICO、data URI 以及校验过的 Base64；支持嵌套 binary 叶子。

**原始字节与导出**

- 详情中的非图片二进制，或右键「查看原始字节」，打开 Hex + ASCII 搜索。
- 导出 CSV、JSON、Excel、Markdown、SQL 与 Parquet 碎片；可批量提取图片。

**界面**

- 浅色 / 深色 / 跟随系统，中英文切换。
- 菜单、下拉、表格与消息窗口使用同一套圆角设计系统。

## 下载

Windows 用户推荐直接安装 [最新 Release 中的 `ParqScan-Windows-Setup.exe`](https://github.com/SELFEMO/ParqScan/releases/latest/download/ParqScan-Windows-Setup.exe)。该链接始终指向最新版本，无需随版本号手动更新。

## 安装与运行

需要 Python 3，以及 [requirements.txt](requirements.txt) 中的依赖（PySide6、PyArrow、openpyxl、psutil）。

```bash
python -m pip install -r requirements.txt
python main.py
```

打开指定文件：

```bash
python main.py sample.parquet
```

## 测试

```bash
python -m unittest discover -s tests -v
```

## 打包

**推荐在干净的 pip 虚拟环境中构建。** 若在 Anaconda base 等环境中直接运行 `python build.py`，PyInstaller 可能沿依赖图拉入 pandas、notebook、MKL 等无关包，导致 `dist/ParqScan` 膨胀到约 1 GB 以上。干净环境通常约 250–450 MB。

发布用干净构建（推荐，体积更小）：

```powershell
winget install --id Python.Python.3.12 -e
.\scripts\build_windows.ps1
```

本地 Conda 环境（`py312`）快速构建（cmd）：

```bat
scripts\build_windows.cmd
```

若本机同时装有多个 Python，PowerShell 脚本可指定：`$env:PARQSCAN_BUILD_PYTHON = "C:\Path\To\python.exe"`

手动构建：

```bash
python build.py
python build.py --installer
```

Windows 默认目录模式，产物为 `dist/ParqScan/ParqScan.exe`；`python build.py --installer` 会额外生成 `dist/installer/ParqScan-Windows-Setup.exe`（需先安装 [Inno Setup 6](https://jrsoftware.org/isdl.php)）。若 PyInstaller 已完成，可单独打安装包：

```bash
python build.py --installer-only
```

安装 Inno Setup 示例：`winget install --id JRSoftware.InnoSetup -e`

需要单文件时使用 `python build.py --onefile`；启动失败排查可用 `python build.py --debug`。构建配置固定 PySide6，并为 Conda 环境补收集 PyArrow 动态库（Conda 构建会打印警告，发布包仍应在 pip venv 或 CI 中生成）。生产构建若启动失败，错误写入用户应用数据目录 `ParqScan/logs/startup.log`。

本地验证体积：

```powershell
Get-ChildItem dist\ParqScan -Recurse | Measure-Object -Property Length -Sum
```

打 tag（如 `v0.3.1`）后，GitHub Actions 会自动构建并上传 Windows 安装包到 Release；若 onedir 超过 600 MB 则 CI 失败。发布前请运行 `python scripts/sync_release_metadata.py` 同步文档与 README 中的版本号。

桌面端（Windows 安装版）支持帮助菜单「检查更新」，并在启动后每日最多自动检查一次；发现新版本后需用户确认才会下载并安装。

## 可移植配置

默认配置在用户应用数据目录。在程序目录放置空文件 `portable.flag` 后，配置改为保存在程序目录。分页大小、主题、语言、最近文件、侧栏排序和列顺序会自动保存。

## 文档

- [GitHub Pages 站点](docs/index.html)：产品首页与使用说明（静态文件位于 `docs/`，启用后访问 `https://<user>.github.io/ParqScan/`）。
- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)：架构、模块职责与行为边界。
- [PROJECT_RECORD.md](PROJECT_RECORD.md)：按日期的重要变更记录。

### 启用 GitHub Pages

1. 打开仓库 **Settings → Pages**。
2. **Build and deployment → Source** 选择 **Deploy from a branch**。
3. **Branch** 选择默认分支（通常为 `main`），**Folder** 选择 **`/docs`**，保存。
4. 等待部署完成后，站点地址为 `https://<github-username>.github.io/ParqScan/`（本仓库用户名为 `SELFEMO` 时即 `https://selfemo.github.io/ParqScan/`）。

本地预览：

- 可直接双击打开 `docs/index.html` 或 `docs/guide.html`（文案内嵌在 `docs/js/i18n.js`，不依赖本地服务器）。
- 若需模拟 GitHub Pages 路径，可运行 `python -m http.server 8080 --directory docs`，然后打开 `http://localhost:8080/`。

修改文案时，请同步更新 `docs/i18n/zh.json`、`docs/i18n/en.json`，并重新生成 `docs/js/i18n.js`（两者需保持一致）。

## License

Copyright 2026 ParqScan contributors.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

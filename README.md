# ParqScan

当前版本 **0.2.5**。许可证：[Apache License 2.0](LICENSE)。

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

```bash
python build.py
```

Windows 默认目录模式，产物为 `dist/ParqScan/ParqScan.exe`。需要单文件时使用 `python build.py --onefile`；启动失败排查可用 `python build.py --debug`。构建配置固定 PySide6，并为 Conda 环境补收集 PyArrow 动态库。生产构建若启动失败，错误写入用户应用数据目录 `ParqScan/logs/startup.log`。

## 可移植配置

默认配置在用户应用数据目录。在程序目录放置空文件 `portable.flag` 后，配置改为保存在程序目录。分页大小、主题、语言、最近文件、侧栏排序和列顺序会自动保存。

## 文档

- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)：架构、模块职责与行为边界。
- [PROJECT_RECORD.md](PROJECT_RECORD.md)：按日期的重要变更记录。

## License

Copyright 2026 ParqScan contributors.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

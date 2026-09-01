# ParqScan 项目总览

本文说明架构、模块职责与行为边界。安装、运行与功能清单见 [README.md](README.md)；按日期的改动见 [PROJECT_RECORD.md](PROJECT_RECORD.md)。

## 一、目标与架构

ParqScan 使用 Python、PySide6 与 PyArrow，在不把完整大文件物化到内存的前提下，提供元数据查看、分页浏览、嵌入图片预览、二进制附件检查与常见格式导出。

五层结构：

1. **应用层**：QApplication、配置、语言、主题与主窗口生命周期。
2. **数据层**：Parquet 元数据、按页读取逻辑行、流式导出与后台任务。
3. **模型层**：只保存当前页 Arrow Table，另存全局搜索坐标和文件级排序行号索引，向表格提供显示与图片角色。
4. **界面层**：主窗口、元数据页、数据页、详情窗口、原始字节工具与设计系统。
5. **工具层**：嵌套二进制提取、图片解码、序列化、资源定位与程序化图标。

数据流：

```text
打开文件
  → ParquetDocument 读取 Schema 与文件元数据
  → ParquetTableModel 请求当前页
  → PageLoadTask 在线程池中调用 read_rows()
  → 当前页 Arrow Table 回到模型
  → QTableView 绘制文本或按需解码缩略图
```

## 二、当前关键逻辑

### 1. 固定分页与内存

- 每页 20、50、100 或 200 行；模型只持有当前页一个 `pa.Table`。
- 翻页、改页大小或关闭文档会取消旧任务并释放旧页与缩略图 / 悬停图缓存。
- 后台任务用代次隔离，过期结果不能覆盖当前页。
- `ParquetDocument.read_rows()` 跳过无交集行组，只切目标逻辑窗口；`close()` 关闭底层 `ParquetFile`。

### 2. 行选择与详情画布

- 单击选中整行；双击打开 `RecordDetailDialog`，打开时快照源行各列值。
- 左侧多选字段；右侧 `AdaptivePreviewGrid` 为普通 `QWidget` 画布。新格叠在 `(0, 0)` 并置顶，已有格位置与大小不变。
- `PreviewTile` 实心不透明，圆角由 mask 裁切，描边画在圆角路径上。标题条是唯一拖动手柄。
- 打开详情、双击或主窗失焦时关闭主表图片悬停卡。
- 字符串字段若整段为 JSON 对象或数组，详情里按层级缩进；标量与无效 JSON 保持原文。完整值不走平台 Tooltip。

### 3. 图片与嵌套二进制

`contains_binary_type()` 递归检查 binary、Struct、List、Map、Dictionary。运行时由 `iter_binary_candidates()` 找叶子。

```text
嵌套值 → 二进制候选 → Magic Bytes / data URI / Base64
  → QImageReader 按目标尺寸解码
  → 72px 表格缩略图、520px 悬停缓存，或详情完整 QImage
```

详情与独立预览共用 `ZoomableImageView`：源图只解码一次，缩放只改视图矩阵。完整解码仅在用户打开详情时发生。

### 4. 原始字节

非图片二进制在详情格或右键「查看原始字节」中打开 Hex + ASCII。搜索有显式按钮；自动模式把偶数长度十六进制当作 Hex；匹配在原始 bytes 上按字节推进并保留重叠。

### 5. 设计系统

顶层菜单与下拉必须用蒙版裁切圆角（QSS `border-radius` 不够）。`RoundedMenu`、`RoundedComboBox`、`RoundedTableView`、`MessageDialog`、`SearchField`、`PaginationBar` 承担真实裁切、无原生长 Tooltip、图标分页。

## 三、目录与文件职责

### 根目录

| 文件 | 职责 |
| --- | --- |
| `main.py` | 入口；冻结程序启动诊断；`--smoke-test` |
| `build.py` | PyInstaller 构建与冒烟测试 |
| `ParqScan.spec` | 冻结配置的唯一来源 |
| `requirements.txt` | PySide6、PyArrow、openpyxl、psutil |
| `LICENSE` / `NOTICE` | Apache 2.0 |
| `README.md` | 使用说明 |
| `PROJECT_OVERVIEW.md` | 本文 |
| `PROJECT_RECORD.md` | 变更记录 |

### 应用与配置

- `parqscan/application.py`：生命周期、命令行路径、Windows AppId。
- `parqscan/config.py`：便携或用户目录 JSON 配置。
- `parqscan/constants.py`：分页、缩略图 / 悬停尺寸、行高、导出批次。
- `parqscan/i18n.py` / `themes.py`：中英文与浅色 / 深色 / 跟随系统。
- `parqscan/main_window.py`：多文件工作区、菜单、导出 Worker、关于窗口、拖拽。

### 数据与模型

- `parqscan/data/parquet_document.py`：Schema、行组、范围读取、`close()`。
- `parqscan/data/page_loader.py`：单页后台任务，结束时关闭临时文档。
- `parqscan/data/export_service.py`：CSV / JSON / Excel / Markdown / SQL / Parquet 碎片。
- `parqscan/data/workers.py`：导出与图片提取 Worker。
- `parqscan/models/parquet_table_model.py`：当前页模型；`image_pixmap` 分 72 / 520 缓存。

### 工具

- `parqscan/utils/binary.py`：格式识别、嵌套载荷、Hex / Base64。
- `parqscan/utils/qt_images.py`：`decode_image_bytes`。
- `parqscan/utils/serialization.py`：`pretty_text` / `json_safe`。
- `parqscan/utils/icons.py`、`search.py`、`paths.py`。

### 界面

- `parqscan/widgets/design_system.py`：卡片、圆角表 / 菜单 / 下拉、`ZoomableImageView`、分页、消息窗。
- `parqscan/widgets/document_widget.py`：元数据 + 数据预览。
- `parqscan/widgets/data_widget.py`：分页、搜索范围、筛选、详情、右键、悬停预览。
- `parqscan/widgets/metadata_widget.py`、`binary_delegate.py`、`image_popup.py`。
- `parqscan/dialogs/cell_detail_dialog.py`：记录详情画布。
- `parqscan/dialogs/hex_dialog.py`、`range_export_dialog.py`。

### 资源与测试

- `parqscan/locales/zh.json`、`en.json`（键集合必须一致）。
- `parqscan/styles/light.qss`、`dark.qss`。
- `parqscan/resources/ParqScan.svg`、`release.json`。
- `tests/`：`test_binary`、`test_serialization`、`test_parquet_document`、`test_locales`、`test_ui_assets`、`test_build`。

## 四、行为边界

- 当前页筛选和复制整列只作用于本页；文件搜索与列头排序会扫整个文件。
- 表头不提供完整全局排序（只有行号索引重排）。
- 图片完整解码只在打开详情时执行。
- 原始字节工具只对含 binary 叶子的字段可用。

## 五、待验证

- Windows / Linux / macOS 上完整 GUI 与 PyInstaller 产物。
- 不同 DPI 下菜单与下拉蒙版边缘。
- 超宽 Schema、大图、损坏图片。

## 六、实现专题

### 控件几何

`MessageDialog` 用内容驱动高度，避免高 DPI 下大块留白。`RoundedComboBox` 在 `contentsRect` 内绘制当前值，不依赖 `SC_ComboBoxEditField`。关于窗口使用应用 Logo。

### 图片链路

表格 72px 与悬停 520px 分 LRU 缓存。详情 `decode_image_bytes(..., maximum_size=None)` → `ZoomableImageView.set_source_image()`；`OriginalImageItem` 画完整 QImage。缩略图缓存不得进入详情。

### 详情 JSON

`FieldPreviewPane._render_value()` → `pretty_text()`：原生容器直接缩进；字符串仅在整段为对象或数组时解析。不改变表格预览、导出、筛选、搜索的数据语义。

### 搜索与筛选

文件搜索完成只更新匹配坐标与高亮，不自动清筛选。页内搜索只扫当前可见偏移。`PageFilterState` 在翻页后重建筛选。导航时若匹配被筛选隐藏，提示用户而不是静默恢复未筛选页。异步回调校验代次、查询、范围与是否自动定位。

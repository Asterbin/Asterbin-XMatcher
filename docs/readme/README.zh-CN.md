<div align="center">

# XMatcher

**本地 XRD 物相识别工具包与 App**

**当前版本：V1.1.0**

[![GitHub stars](https://img.shields.io/github/stars/Asterbin/Asterbin-XMatcher?style=social)](https://github.com/Asterbin/Asterbin-XMatcher/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/Asterbin/Asterbin-XMatcher)](https://github.com/Asterbin/Asterbin-XMatcher/issues)
[![说明手册](https://img.shields.io/badge/Guide-online-2563eb)](https://asterbin.github.io/Asterbin-XMatcher)
[![下载](https://img.shields.io/badge/Download-App%20%26%20Data-0f766e)](https://doi.org/10.6084/m9.figshare.32812985)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)

**Language / 语言 / 言語 / 언어**  
[English](../../README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

</div>

XMatcher 是用于实验粉末 X 射线衍射（XRD）物相识别的本地软件与 Python 工具包。它的核心流程是：先构建或下载理论峰数据库，然后对实验谱进行寻峰、匹配、候选排序和结果解释。

## App 下载

多数用户推荐直接下载封装好的 XMatcher App。App 版本会自动连接本地服务，用户不需要手动运行 `xmatcher_local_api.py`。

- App、数据库和发布文件：https://doi.org/10.6084/m9.figshare.32812985
- 在线手册：https://asterbin.github.io/Asterbin-XMatcher
- 问题反馈：https://github.com/Asterbin/Asterbin-XMatcher/issues

如果你直接使用源码或 HTML 版本，需要先启动本地 API：

```bash
python xmatcher_local_api.py --database MP500_xrd_database.pkl
```

然后打开 [`XMatcher_Local_UI.html`](../../XMatcher_Local_UI.html)。

## 功能概览

- 读取常见两列 XRD 文件，例如 CSV、TXT、XY、DAT。
- 自动去背底、平滑、寻峰，并筛选代表性实验峰。
- 支持按元素过滤数据库，减少误匹配并加快检索。
- 使用峰位、强度、覆盖率和整体 2θ 平移进行候选排序。
- App 支持实验谱与理论峰对比、局部放大、图像编辑、PNG/SVG 导出。
- PDF 全峰对比模块支持最多五个 CIF 的多相加权混合对比。
- AutoMix 自动多相识别会从单相候选中搜索最多三个相的组合，以非负拟合给出相对衍射贡献、峰归属和未解释残峰；贡献值不等同于质量分数。

## AutoMix 自动多相识别（V1.1.0）

当单相候选无法解释主要实验峰时，可使用 AutoMix。它从前列单相候选中搜索最多三个相的组合，并通过非负拟合估计各保留相的相对衍射贡献。该贡献值描述拟合到的衍射信号，**不等同于质量分数或重量百分比**。

1. 先完成单相自动识别，再展开“AutoMix 自动多相识别”。
2. 设置最多相数和适中的“候选池”。候选池是用于组成相组合的前列单相候选数量；设得过大会使组合数快速增加、计算变慢，并可能引入近似重复结果。
3. 运行 AutoMix 后，点击不同组合进行比较。图中会显示实验谱、按贡献缩放的理论峰、未解释残峰，以及每个相位于图谱下方独立轨道中的完整理论峰列表。
4. 可在 AutoMix 图中框选局部范围放大；结合检测峰归属表判断结果，并使用 PDF 全峰对比模块上传 CIF 做最终确认。

AutoMix 会按最终实际参与拟合的数据库物相去重，零贡献候选相不会再作为重复结果显示。

## 项目文件

| 文件 | 用途 |
| --- | --- |
| [`XMatcher_Guide.html`](../../XMatcher_Guide.html) | 正式中英文手册，包含代码、App 和常见问题模块。 |
| [`XMatcher_Local_UI.html`](../../XMatcher_Local_UI.html) | 本地交互式 XRD 识别界面。 |
| [`xmatcher_local_api.py`](../../xmatcher_local_api.py) | HTML 界面使用的本地 Python API。 |
| [`XMatcher_Jupyter_API_Guide_CN_EN.ipynb`](../../XMatcher_Jupyter_API_Guide_CN_EN.ipynb) | Jupyter API 示例。 |
| [`build_database_parallel.py`](../../build_database_parallel.py) | 从 `MP500.db` 构建 `MP500_xrd_database.pkl`。 |
| [`XMatcher/`](../../XMatcher/) | Python 包源码。 |

## 快速开始：Python API

```python
from XMatcher import XRDRetriever

retriever = XRDRetriever(
    database_path="MP500_xrd_database.pkl",
    n_peaks=20,
    position_tolerance=0.2,
    scoring_method="hybrid",
)

results = retriever.retrieve_from_file(
    "exp_data/BTc.csv",
    elements=["B", "Tc"],
    element_filter_mode="exact",
    top_n=3,
)

retriever.print_results(results)
```

## 引用说明

如果本软件支持了您的研究，请引用以下论文：

Cao B., Zheng Z., Liu Y., Zhang L., Wong L. W. Y., Weng L.-T., Li J., Li H., and Zhang T.-Y. XQueryer: an intelligent crystal structure identifier for powder X-ray diffraction. *National Science Review* 12(12), nwaf421 (2025).

## License

This project is licensed under the MIT License. See [`LICENSE`](../../LICENSE).

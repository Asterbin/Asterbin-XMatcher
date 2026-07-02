<div align="center">

# XMatcher

**本地 XRD 物相识别工具包与 App**

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

XMatcher 并非 XQueryer 本身，而是作为 XQueryer 相关研究工作的一部分开发和整理的本地 XRD 物相识别软件。目前 XMatcher 没有单独发表论文。如果本软件支持了您的研究，建议引用 XQueryer 论文：

Cao B., Zheng Z., Liu Y., Zhang L., Wong L. W. Y., Weng L.-T., Li J., Li H., and Zhang T.-Y. XQueryer: an intelligent crystal structure identifier for powder X-ray diffraction. *National Science Review* 12(12), nwaf421 (2025).

## License

This project is licensed under the MIT License. See [`LICENSE`](../../LICENSE).

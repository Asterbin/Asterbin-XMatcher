<div align="center">

# XMatcher

**ローカル XRD 相同定ツールキット & App**

[![GitHub stars](https://img.shields.io/github/stars/Asterbin/Asterbin-XMatcher?style=social)](https://github.com/Asterbin/Asterbin-XMatcher/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/Asterbin/Asterbin-XMatcher)](https://github.com/Asterbin/Asterbin-XMatcher/issues)
[![Guide](https://img.shields.io/badge/Guide-online-2563eb)](https://asterbin.github.io/Asterbin-XMatcher)
[![Download](https://img.shields.io/badge/Download-App%20%26%20Data-0f766e)](https://doi.org/10.6084/m9.figshare.32812985)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)

**Language / 语言 / 言語 / 언어**  
[English](../../README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

</div>

XMatcher は、実験粉末 X 線回折（XRD）パターンを理論ピークデータベースと照合するためのローカルソフトウェアおよび Python ツールキットです。理論ピークデータベースを一度準備し、実験パターンのピーク検出、照合、候補順位付け、結果解釈を行います。

## App ダウンロード

通常の利用では、パッケージ化された XMatcher App を推奨します。App 版はローカルサービスへ自動接続するため、ユーザーが `xmatcher_local_api.py` を手動で起動する必要はありません。

- App、データベース、リリースファイル：https://doi.org/10.6084/m9.figshare.32812985
- オンラインマニュアル：https://asterbin.github.io/Asterbin-XMatcher
- Issues：https://github.com/Asterbin/Asterbin-XMatcher/issues

ソースコードまたは HTML 版を直接使う場合のみ、先にローカル API を起動します。

```bash
python xmatcher_local_api.py --database MP500_xrd_database.pkl
```

その後、[`XMatcher_Local_UI.html`](../../XMatcher_Local_UI.html) を開きます。

## 主な機能

- CSV、TXT、XY、DAT などの一般的な 2 列 XRD ファイルを読み込み。
- 背景除去、平滑化、ピーク検出、代表的な実験ピークの選択。
- 元素フィルタによる候補削減と高速化。
- ピーク位置、強度、カバレッジ、全体 2θ シフトに基づく候補順位付け。
- App ではズーム、プロット編集、PNG/SVG エクスポートに対応。
- PDF 全ピーク比較モジュールでは最大 5 個の CIF による多相混合比較が可能。

## 主要ファイル

| ファイル | 用途 |
| --- | --- |
| [`XMatcher_Guide.html`](../../XMatcher_Guide.html) | 正式ユーザーガイド。 |
| [`XMatcher_Local_UI.html`](../../XMatcher_Local_UI.html) | ローカル XRD 識別 UI。 |
| [`xmatcher_local_api.py`](../../xmatcher_local_api.py) | UI 用ローカル Python API。 |
| [`XMatcher_Jupyter_API_Guide_CN_EN.ipynb`](../../XMatcher_Jupyter_API_Guide_CN_EN.ipynb) | Jupyter API 例。 |
| [`build_database_parallel.py`](../../build_database_parallel.py) | 理論ピークデータベース構築スクリプト。 |
| [`XMatcher/`](../../XMatcher/) | Python パッケージソース。 |

## Python API クイックスタート

```python
from XMatcher import XRDRetriever

retriever = XRDRetriever(
    database_path="MP500_xrd_database.pkl",
    n_peaks=20,
    position_tolerance=0.2,
    scoring_method="hybrid",
)

results = retriever.retrieve_from_file("exp_data/BTc.csv", top_n=3)
retriever.print_results(results)
```

## 引用について

XMatcher は XQueryer そのものではありません。XQueryer 関連研究の一部として開発・整理されたローカル XRD 相同定ソフトウェアです。現時点で XMatcher 単独の論文はありません。本ソフトウェアが研究に役立った場合は、XQueryer 論文の引用を推奨します。

Cao B., Zheng Z., Liu Y., Zhang L., Wong L. W. Y., Weng L.-T., Li J., Li H., and Zhang T.-Y. XQueryer: an intelligent crystal structure identifier for powder X-ray diffraction. *National Science Review* 12(12), nwaf421 (2025).

## License

This project is licensed under the MIT License. See [`LICENSE`](../../LICENSE).

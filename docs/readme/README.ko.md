<div align="center">

# XMatcher

**로컬 XRD 상 식별 툴킷 & App**

[![GitHub stars](https://img.shields.io/github/stars/Asterbin/Asterbin-XMatcher?style=social)](https://github.com/Asterbin/Asterbin-XMatcher/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/Asterbin/Asterbin-XMatcher)](https://github.com/Asterbin/Asterbin-XMatcher/issues)
[![Guide](https://img.shields.io/badge/Guide-online-2563eb)](https://asterbin.github.io/Asterbin-XMatcher)
[![Download](https://img.shields.io/badge/Download-App%20%26%20Data-0f766e)](https://doi.org/10.6084/m9.figshare.32812985)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)

**Language / 语言 / 言語 / 언어**  
[English](../../README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

</div>

XMatcher는 실험 분말 X선 회절(XRD) 패턴을 이론 피크 데이터베이스와 비교하여 상을 식별하는 로컬 소프트웨어 및 Python 툴킷입니다. 이론 피크 데이터베이스를 준비한 뒤 실험 패턴의 피크 검출, 매칭, 후보 순위화, 결과 해석을 수행합니다.

## App 다운로드

일반 사용자는 패키징된 XMatcher App 사용을 권장합니다. App 버전은 로컬 서비스에 자동으로 연결되므로 사용자가 `xmatcher_local_api.py`를 직접 실행할 필요가 없습니다.

- App, 데이터베이스, 릴리스 파일: https://doi.org/10.6084/m9.figshare.32812985
- 온라인 매뉴얼: https://asterbin.github.io/Asterbin-XMatcher
- Issues: https://github.com/Asterbin/Asterbin-XMatcher/issues

소스 코드 또는 HTML 버전을 직접 사용하는 경우에만 로컬 API를 먼저 실행합니다.

```bash
python xmatcher_local_api.py --database MP500_xrd_database.pkl
```

그 다음 [`XMatcher_Local_UI.html`](../../XMatcher_Local_UI.html)을 엽니다.

## 주요 기능

- CSV, TXT, XY, DAT 등 일반적인 두 열 XRD 파일 읽기.
- 배경 제거, 평활화, 피크 검출, 대표 실험 피크 선택.
- 원소 필터를 이용한 후보 축소 및 검색 속도 향상.
- 피크 위치, 강도, 커버리지, 전체 2θ shift 기반 후보 순위화.
- App에서 확대/축소, 플롯 편집, PNG/SVG 내보내기 지원.
- PDF 전체 피크 비교 모듈에서 최대 5개 CIF의 다상 혼합 비교 지원.

## 주요 파일

| 파일 | 용도 |
| --- | --- |
| [`XMatcher_Guide.html`](../../XMatcher_Guide.html) | 공식 사용자 가이드. |
| [`XMatcher_Local_UI.html`](../../XMatcher_Local_UI.html) | 로컬 XRD 식별 UI. |
| [`xmatcher_local_api.py`](../../xmatcher_local_api.py) | UI용 로컬 Python API. |
| [`XMatcher_Jupyter_API_Guide_CN_EN.ipynb`](../../XMatcher_Jupyter_API_Guide_CN_EN.ipynb) | Jupyter API 예제. |
| [`build_database_parallel.py`](../../build_database_parallel.py) | 이론 피크 데이터베이스 빌드 스크립트. |
| [`XMatcher/`](../../XMatcher/) | Python 패키지 소스. |

## Python API 빠른 시작

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

## 인용 안내

XMatcher는 XQueryer 자체가 아닙니다. XQueryer 관련 연구의 일부로 개발 및 정리된 로컬 XRD 상 식별 소프트웨어입니다. 현재 XMatcher 단독 논문은 없습니다. 이 소프트웨어가 연구에 도움이 되었다면 XQueryer 논문을 인용하는 것을 권장합니다.

Cao B., Zheng Z., Liu Y., Zhang L., Wong L. W. Y., Weng L.-T., Li J., Li H., and Zhang T.-Y. XQueryer: an intelligent crystal structure identifier for powder X-ray diffraction. *National Science Review* 12(12), nwaf421 (2025).

## License

This project is licensed under the MIT License. See [`LICENSE`](../../LICENSE).

# 인적신뢰도·인적오류 평가 툴킷

> Version 0.3: the current English documentation is README.md, docs/USER_GUIDE.md and docs/HUMAN_ERROR_DATA.md. This Korean walkthrough retains the initial implementation scope.


작업 분석부터 인적실패확률, 응답시간, 복구, 종속성, FTA·ETA 연결까지
조합할 수 있는 Python 연구용 라이브러리입니다. 버전은 `0.1.0`입니다.
공정별 작업·파라미터·관측 데이터를 교체하고 사용자 추정기를 등록할 수 있습니다.

## 바로 시작

Python 3.12 이상에서 프로젝트 폴더를 열고 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[data,learning,survival,thermo,sensitivity,bdd,dev]"
human-reliability doctor
human-reliability template case.json
human-reliability run case.json --out result.json
python examples/python_api.py
```

예제 확률은 사용 흐름을 설명하기 위한 가정입니다. 실제 평가에서는 작업의
실패 정의, 요구 기회, 조건, 근거, 시간 단위를 먼저 정하고 값을 바꾸어야 합니다.
자세한 절차는 [사용 설명서](docs/USER_MANUAL_KO.md)에 있습니다.

## 구현 범위

| 목적 | 제공하는 기능 |
|---|---|
| 작업 분석 | 선행 관계·역할·작업 종류, 변경 가능한 오류 질문, 잠재위험, 조직·절차·협업 검토 |
| 확률 평가 | 선언값, Beta-Bernoulli 추정, 조건부 인지 단계, SPAR-H·HEART 계산 어댑터 |
| 시간과 복구 | 검열 자료, Kaplan-Meier·Weibull·AFT·Cox, 마감시간, 복구·종속성 |
| 동적 분석 | 자원 제약 작업 실행, 인지·명령·차단 완료 시각 분리, Petri net 탐색 |
| 위험성 연결 | 반복 사건을 보존하는 FTA, 조건부 ETA, LOPA 선별, Bayesian network, 빈도·불확실성 |
| 공정 연결 | 경보·신호 유효성, CoolProp SI 물성, 기존 저장소 객체 어댑터 |

일부 조직·설계 개념은 정성 검토 항목으로 구현했습니다. 범용 HEP 계수로
바꾸지 않았습니다. 계수표가 필요한 기법은 사용자가 검토한 값을 입력합니다.
[기능별 상태](research/capabilities.json)에 계산·정성·확장 범위를 구분했습니다.

## 확보한 데이터와 검증

공개 데이터 15개 계열을 검토하고 9개 계열, 약 1.705 GB를 확보했습니다.
UCI 공정 데이터 6종, TEP, HITL, COG-BCI 행동 자료가 포함됩니다.
출처·이용 조건·체크섬·처리 한계를 기록했고 원자료는 배포물에서 제외합니다.

공정 이상 신호를 인적오류 라벨로 해석하지 않습니다. HITL 평가는 참가자 단위로
훈련·시험을 분리했습니다. COG의 반복 오류 플래그는 의미가 불확실해 HEP
보정에서 보류했습니다. 시험 결과와 반례는 [검증 기록](docs/VALIDATION.md)에
남겨 두었습니다. 현장 HEP 보정이나 방호계층 인증을 완료했다는 의미는 아닙니다.

## 다른 저장소와 연계

PRISM, DynaSense, 수소충전소 시뮬레이터, 모니터링, LH2DT, SAGA,
QSafety 및 PSA 시계열을 연결할 경계를 제공합니다. 실제 객체로 확인한 범위와
수신측 수정이 필요한 부분은 [연계 설명서](docs/INTEGRATION.md)에 있습니다.

## 연구 이어가기

- [사용 설명서](docs/USER_MANUAL_KO.md): 입력 작성과 실행
- [계획](docs/PLAN.md)·[진행 상태](research/progress.json): 목표와 완료 근거
- [API](docs/API.md)·[설계](docs/ARCHITECTURE.md): 코드 연결과 확장
- [기법 설명](docs/METHODS.md)·[데이터](docs/DATA.md): 적용 범위와 조건
- [개발 지침](docs/DEVELOPER_HANDBOOK.md)·[개발 기록](docs/DEVELOPMENT_LOG.md)
- [연구 인수인계](docs/RESEARCH_HANDOFF.md): 재현 명령과 다음 연구 과제
- [이용 조건](docs/LICENSING.md)·[외부 출처](docs/SOURCES.md)

원본 기여물은 MIT로 배포할 수 있도록 구성했습니다. 외부 데이터·라이브러리의
조건은 각각 유지됩니다. 패키징 검사는 파일 경계를 확인하며 모든 권리 문제에
대한 법적 보증을 제공하지 않습니다.

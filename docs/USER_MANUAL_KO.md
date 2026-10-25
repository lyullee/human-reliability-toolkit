# 인적신뢰도 평가 사용 설명서

> Version 0.2: the current English documentation is README.md, docs/USER_GUIDE.md and docs/HUMAN_ERROR_DATA.md. This Korean walkthrough retains the initial implementation scope.


Human Reliability Toolkit은 작업 절차를 분석하고, 특정 작업 요구에서 정의한 인적실패사건의 확률·복구·시간·종속성을 계산하는 Python 연구 라이브러리다. 결과는 작업과 조건에 관한 값이다. 개인의 일반적인 신뢰도를 나타내는 점수로 사용하지 않는다.

## 설치와 첫 실행

Python 3.12 이상을 사용한다. 저장소 폴더에서 독립 환경을 만들고 필요한 선택 기능을 설치한다.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[data,learning,survival,thermo,sensitivity,bdd,dev]"
.venv\Scripts\python examples/python_api.py
.venv\Scripts\python -m human_reliability template input.json
.venv\Scripts\python -m human_reliability run input.json --out result.json
```

일반 Python 환경에서는 `python` 명령으로 동일한 스크립트를 실행하면 된다. 핵심 평가에는 NumPy, SciPy와 Pydantic만 필요하다. `data`는 자료 읽기, `learning`은 실험 결과 예측, `survival`은 검열 자료와 공변량을 이용한 응답시간 회귀, `thermo`는 CoolProp, `sensitivity`는 SALib, `bdd`는 큰 Boolean 트리를 위한 선택 기능이다. `dev`는 개발 검증 도구다.

`requirements-validated.txt`는 기록된 Windows 개발 환경이다. 모든 운영체제와 외부 프로젝트가 같은 의존성 환경을 공유할 수 있다는 뜻은 아니다. 최소 환경에서 시작하고 필요한 선택 기능만 추가할 수 있다.

## 입력을 만드는 순서

1. 작업 요구를 정의한다. “경보 1건”, “정비 후 재가동 1회”처럼 실패확률의 분모가 되는 기회를 정한다.
2. 승인된 작업 절차와 실제 수행 과정을 확인한다. 작업 단계에 담당자, 대상, 시작 단서, 선행 단계, 완료조건을 기록한다.
3. 오류 형태와 원인·잠재위험을 구분한다. 단계 누락과 잘못된 대상 선택은 오류 형태이고, 불명확한 표시는 가능한 원인이다.
4. 인적실패사건을 정의한다. 최초 오류인지, 복구하지 못한 오류인지, 일정 시간 안에 완료하지 못한 대응인지 분명히 한다.
5. 방법과 근거를 선택한다. 관측 자료, 문헌 수치, 전문가 판단과 가정을 서로 구분한다.
6. 필요한 경우 복구와 응답시간을 추가한다. 이미 포함된 효과를 다시 적용하면 API가 거부한다.
7. FTA·ETA 또는 공정모델에 사건·조건·시간과 함께 전달한다.

제공되는 입력 예제의 수치는 소프트웨어 사용법을 보여주기 위해 작성한 가정이다. 실제 수소충전소 또는 특정 인력 집단의 측정값이 아니다.

## 작업 모델

`Task`는 절차 버전, 단계와 근거를 묶는다. `TaskStep`은 다음 정보를 갖는다.

| 필드 | 의미 |
|---|---|
| `id` | 단계의 안정적인 식별자 |
| `action`, `target`, `actor` | 수행 동작, 대상과 담당 역할 |
| `kind` | 관측·식별·판단·의사소통·조작·확인·복귀 중 하나 |
| `cue`, `completion` | 시작 단서와 물리적·업무적 완료조건 |
| `predecessors` | 완료되어야 하는 선행 단계 |
| `preconditions`, `latent_hazards` | 필요한 상태와 숨어 있을 수 있는 위험 |
| `deadline_s` | 에피소드 시작 기준 완료 기한 |
| `processing_mode` | 숙련·규칙·지식 기반 또는 혼합 처리에 대한 분류 |

처리 모드 자체는 오류확률 배수가 아니다. 단계 그래프에 순환이나 존재하지 않는 선행 단계가 있으면 입력을 거부한다. 반복 운전은 별도 에피소드 또는 `WorkflowNet`의 상태전이로 표현한다.

## 오류 후보와 정성 검토

기본 규칙 18개는 단계에 적용 가능한 질문을 생성한다. 결과의 `candidate`는 확인된 오류나 실제 원인이 아니다. 분석자는 `confirmed`, `excluded`, `needs_information` 등의 상태와 근거를 남길 수 있다.

`analyze_task(task, rules=..., exclusions=...)`로 규칙을 교체한다. JSON 사례의 `deviation_rules`도 동일한 입력을 받는다. 제외하려면 해당 후보 ID와 구체적인 이유가 필요하다. 잠재위험은 의도한 조작을 해도 안전하지 않을 수 있는 조건으로 별도 기록한다.

절차 품질, 조직·관리, 교대 인수인계, 협업, 우회 운전, 인터페이스 설계는 `Review`와 `ReviewItem`으로 평가한다. “불명확함”과 “해당 없음”을 구별하며, 검토 항목을 자동으로 보편적 HEP 배수로 바꾸지 않는다.

## 확률 방법 선택

| 입력 조건 | 방법 |
|---|---|
| 실패와 작업 기회를 같은 기준으로 관측 | `BetaPrior.posterior` 또는 `empirical` 사례 방법 |
| 외부에서 검토한 확률과 적용 근거 보유 | `declared` |
| 인지 단계별 조건부 확률 보유 | `cognitive_chain` |
| SPAR-H의 검토된 8개 요인 배수 보유 | `spar_h` 산술 어댑터 |
| HEART 형식의 명목값·최대효과·적용비율 보유 | `heart` 산술 어댑터 |
| 다른 계산법이 필요 | `AssessmentEngine.register`로 사용자 방법 등록 |

SPAR-H와 HEART 함수는 입력 계수를 계산에 적용하는 기능이다. 과업별 계수표, 현장 적용성 판정 또는 공식 도구 인증을 포함하지 않는다. IDHEAS의 인지 기능 구분은 사건 구조 설계에 참고했으며, `cognitive_chain`을 공식 IDHEAS-ECA 정량 구현으로 부르지 않는다.

Beta 갱신은 동일한 원래 사전분포와 누적 관측 스냅샷에서 다시 계산한다. 같은 자료를 여러 번 증분 입력하지 않는다. 작업 반복과 인력 군집이 있으면 단순 독립 시행 가정을 검토하고, `cluster_bootstrap_rate` 등 군집 불확실성 분석을 함께 사용한다. 실패 0건은 확률이 정확히 0이라는 근거가 아니다.

## 복구와 종속성

`apply_recovery`의 두 번째 입력은 최초 오류가 발생했다는 조건에서 복구하지 못할 확률이다. 오류 발생확률과 같은 사람이 점검에 실패할 확률을 무조건 독립으로 곱하지 않는다.

`conditional_dependency`는 선행 실패가 있다는 조건의 종속성 보정을 계산한다. 입력 수준은 상관계수가 아니다. 같은 인력, 절차, 단서, 팀 또는 공통 장비 때문에 연속 실패가 연결될 수 있다. 공통 상황이 여러 사건을 좌우하면 `BayesianNetwork`의 조건부 확률표를 구성해 FTA의 공동 상태 분포로 전달할 수 있다.

## 응답시간과 기한

`LognormalTime`, `WeibullTime`, `KaplanMeierTime`을 사용할 수 있다. 관측 종료까지 완료하지 못한 응답은 완료시간으로 대체하지 않고 우측 검열로 기록한다. 잘못된 조작으로 끝난 사례는 단순 검열과 다르므로 별도의 실패 사건으로 다룬다.

`KaplanMeierTime`은 마지막 검열 관측 뒤의 분포를 임의로 연장하지 않는다. `fit_weibull_censored`와 `CensoredRegression`은 매개변수 모형의 가정을 사용한다. 회귀에는 명시적으로 초 단위와 실제 완료 여부를 제공해야 한다. 후자는 Weibull AFT와 Cox 모형을 지원한다.

`apply_deadline`은 최초 실패와, 그렇지 않은 대응이 기한을 넘길 확률을 결합한다. `response_bins`는 완료시간 구간과 해석기간 내 미완료를 상호배타적인 분기로 반환한다. 미완료 분기를 영구적인 작동 실패로 해석하지 않는다.

경보 발생, 화면 표시, 사람의 인지, 진단, 명령, 실제 구동 완료를 구분한다. `station_stop_requested`는 명령 시각을 연결하고, `dynasense_scenario`는 물리적 차단 완료시각을 연결한다.

## 위험성 평가 연결

FTA는 동일한 사건 ID를 여러 경로에서 재사용할 수 있다. 기본 `enumerate`는 최대 20개 고유 사건을 정확하게 계산하며, 더 큰 트리에는 `backend="bdd"`를 사용한다. 기본 계산은 고유 기본사건 사이의 독립을 가정한다. 종속성이 있으면 완전한 공동 상태 분포를 사용한다.

ETA의 형제 분기는 조건부 확률 합이 1이어야 한다. 자동 성공·수동 성공·실패 등의 모든 경로를 포함한다. 개시빈도는 한 번만 배분한다. `individual_risk_rate`와 `fn_curve`에는 이미 기상·점화·재실이 어느 단계에 반영되었는지 확인한 결과를 준다.

`lopa_screen`은 공통 의존성이 있거나 인간 대응의 시간적 실행 가능성이 확인되지 않으면 보호 효과를 보류한다. `RiskMatrix`의 등급은 정성 분류이며 확률이 아니다.

## 공개 데이터 사용

```powershell
python scripts/acquire_data.py
python scripts/audit_data.py
python scripts/run_studies.py
python examples/process_context.py
```

기본 획득은 약 1.7 GB의 선택 자산을 보관한다. 전체 파일을 받는 공정 자료와, 대용량 압축파일에서 행동 기록만 받는 자료를 구분한다. `--only hitl cog_bci` 등으로 필요한 자료만 선택할 수 있다. 원본 데이터는 소스 배포에 포함되지 않는다.

제어실 사례는 참가자 단위로 학습과 평가를 나누고 실험 결과 레이블을 예측한다. 현장 HEP를 학습했다는 의미는 아니다. 인지 자료의 동일 위치 오류 플래그는 보정 용도에서 보류했다. 단위와 분모가 확인되지 않은 열은 실제 물리 기한이나 HEP의 입력으로 자동 변환하지 않는다. 자세한 기록은 `docs/DATA.md`를 따른다.

## 오류 해결

- `unsupported method`: 등록된 이름과 내장 방법 이름을 확인한다.
- `already included`: 입력 사건과 추정값에 시간·복구 효과가 이미 들어 있는지 확인한다.
- `unknown or missing evidence`: 사례의 `task.evidence`에 해당 근거를 넣고 적용 범위를 설명한다.
- `clock must strictly increase`: 독립 에피소드 또는 주기마다 초기화된 시간을 하나의 누적 시간으로 합치지 않았는지 확인한다.
- `unidentified censored support`: 자료 범위 안의 기한을 사용하거나 정당화된 매개변수 모형을 별도로 선택한다.
- 선택 라이브러리의 `ImportError`: 해당 extra를 설치한다. 계산 실패를 0으로 대체하지 않는다.

## 연구를 이어갈 때

`docs/RESEARCH_HANDOFF.md`의 실행 순서, `research/protocol.json`의 고정된 분석 규칙, `research/protocol_deviations.json`의 보류 이유를 먼저 읽는다. 결과의 적용 범위를 바꾸려면 입력 정의·계수·자료·검증을 함께 갱신하고 기존 결과를 덮어써서 외부 검증처럼 재사용하지 않는다.

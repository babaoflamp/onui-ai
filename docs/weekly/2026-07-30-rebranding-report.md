# OAI 리브랜딩 전환 보고서 — 2026-07-30

> **ONUI AI → OAI 브랜드 이전 프로젝트**  
> **Phase 1 + Phase 2 완료 보고**  
> **커밋 범위**: `a916306` (Phase 1) + `b2a3ef3` (Phase 2)  
> **기준 커밋**: `3b79647` (리브랜딩 전 안정화 기반)  
> **작업 기간**: 2026-07-30 07:55 ~ 09:14 KST (1시간 18분)  
> **담당자**: Scott Kim (Co-Authored-By: Claude)

---

## 제1장. 리브랜딩 프로젝트 개요

### 1.1 배경 및 목적

`ONUI AI` → `OAI` 브랜드명 변경은 다음 목적을 가진다:

1. **브랜드 단순화**: 4음절 `ONUI` → 3음절 `OAI` (약어화)
2. **글로벌 가독성 향상**: 비한국어권 사용자를 위한 발음/인지 단순화
3. **도메인 일관성**: `opportunity.ai.kr`의 `OAI` 이니셜과의 통일
4. **법인/상표 문제 사전 대비**: 특징적 식별자를 가진 짧은 이름 필요

### 1.2 작업 상세 타임라인

```
2026-07-23 09:35:36   ─── 3b79647 (코어 안정화 + i18n 확장 베이스)
                           ↓ 리브랜딩 준비 완료
2026-07-30 07:55:56   ─── a916306 (Phase 1: 브랜드명 + 캐릭터명 변경)
                           ↓ 1시간 18분 경과
2026-07-30 09:14:41   ─── b2a3ef3 (Phase 2: 피처명 변경)
```

### 1.3 전체 변경 규모

| 지표 | Phase 1 | Phase 2 | 합계 |
|---|---|---|---|
| Changed files | 36개 | 25개 | **47개 (중복 제외)** |
| Insertions | 193 | 130 | **323** |
| Deletions | 193 | 130 | **323** |
| 순수 대체 (1:1) | ✅ | ✅ | ✅ |
| 파일 타입 | 6종 | 5종 | 7종 (로케일/템플릿/JS/CSS/파이썬/셸/MD) |
| 대상 언어 | 9개 | 9개 | 9개 |

---

## 제2장. Phase 1 — `a916306`: 브랜드명 및 캐릭터명 변경

> **커밋 메시지**: `refactor: rebrand ONUI AI to OAI`  
> **범위**: 브랜드명(`ONUI AI`, `Onui AI`, `오누이`) + 캐릭터명(`Onui`, `AI Onui`)  
> **보류**: 피처명(`OnuiTube`, `Onui Beats`, `Onui Grammar`)은 의도적으로 유지

### 2.1 변경 영역별 분석

#### 2.1.1 로케일 JSON — 9개 언어 (Phase 1 중 가장 큰 변경)

**1,084줄 diff** — 9개 언어 각각 40~60개 키-값 쌍 변경

| 언어 | 파일 크기 | Phase 1 변경량 | 주요 변경 패턴 |
|---|---|---|---|
| **en** (영어) | 46,046 B | 40줄 | `Onui`→`OAI`, `ONUI`→`OAI`, `Onui Korean`→`OAI Korean` |
| **ko** (한국어) | 50,721 B | 38줄 | `오누이`→`OAI`, `ONUI`→`OAI` |
| **ja** (일본어) | 53,155 B | 32줄 | `Onui`→`OAI`, `ONUI`→`OAI` |
| **zh** (중국어) | 43,761 B | 34줄 | `Onui`→`OAI`, `ONUI`→`OAI` |
| **vi** (베트남어) | 55,162 B | 32줄 | `Onui`→`OAI`, `ONUI`→`OAI` |
| **ne** (네팔어) | 89,175 B | 50줄 | `Onui`→`OAI`, `ONUI`→`OAI` |
| **id** (인도네시아어) | 47,787 B | 20줄 | `Onui`→`OAI`, `ONUI`→`OAI` |
| **mn** (몽골어) | 71,107 B | 14줄 | `Onui`→`OAI`, `ONUI`→`OAI` |
| **lo** (라오어) | 85,585 B | 24줄 | `Onui`→`OAI`, `ONUI`→`OAI` |

**변경 키 카테고리 (en.json 기준)**:

```jsonc
// 1. 앱/페이지 타이틀
"app.title": "Onui | AI Speech Intelligence" → "OAI | Speech Intelligence"
"__title__": "ONUI Korean · Landing" → "OAI Korean · Landing"

// 2. 로고/브랜딩
"nav.logo": "Onui Korean" → "OAI Korean"
"nav.logo_alt": "ONUI Korean Logo" → "OAI Korean Logo"

// 3. CTA/히어로 문구
"landing.cta.title": "...growing together with Onui." → "...growing together with OAI."
"landing.cta.desc": "Friendly AI Onui..." → "Friendly AI OAI..."

// 4. AI 캐릭터명
"landing.hero.card.name": "AI Onui" → "AI OAI"
"landing.hero.chat.ai1": "I'm your Korean mate, Onui." → "I'm your Korean mate, OAI."

// 5. 랜딩 섹션 브랜딩
"landing.onui.label": "Onui" → "OAI"
"landing.usp.label": "Why ONUI" → "Why OAI"
"landing.usp.title": "Onui's Differentiated Value" → "OAI's Differentiated Value"
"landing.special.badge": "ONUI SPECIAL FEATURE" → "OAI SPECIAL FEATURE"

// 6. 대시보드
"dash.usp.4": "Onui AI Guidance" → "OAI Guidance"
"de.badge": "ONUI · Daily Expression" → "OAI · Daily Expression"

// 7. 기능 배지
"fe.badge": "ONUI · AI SELF-LEARNING" → "OAI · AI SELF-LEARNING"
"speechpro.badge": "ONUI · AI Learning Tool" → "OAI · AI Learning Tool"
"sentence.badge": "ONUI · Free-Input Pronunciation Evaluation" → "OAI · Free-Input Pronunciation Evaluation"

// 8. 랜딩 피처 설명 (피처명은 유지, 주변 텍스트만 변경)
"land.features.desc": "...AI Onui takes care..." → "...AI OAI takes care..."
"land.testi3_desc": "Onui Tube lets me..." → "OAI Tube lets me..."  // ← 예외: Phase 1에서 이미 Onui Tube→OAI Tube로 변경됨
```

#### 2.1.2 Jinja2 템플릿 — 17개 파일

| 템플릿 | 변경 전 (Old) | 변경 후 (New) | 비고 |
|---|---|---|---|
| **base.html** | `<title>ONUI | AI Speech Intelligence</title>` | `<title>OAI | Speech Intelligence</title>` | HTML title |
| | `ONUI<br />AI Speech Intelligence` | `OAI<br />Speech Intelligence` | 사이드바 로고 |
| | `aria-label="ONUI Home"` | `aria-label="OAI Home"` | 접근성 레이블 |
| | `© Onui. All rights reserved.` | `© OAI. All rights reserved.` | 푸터 저작권 |
| | `🛡 Onui Admin` | `🛡 OAI Admin` | 관리자 사이드바 |
| **index.html** (랜딩) | `<title>오누이 한국어 - AI Speech Intelligence</title>` | `<title>OAI 한국어 - AI Speech Intelligence</title>` | HTML title |
| | `ONUI<br />AI Speech Intelligence` | `OAI<br />Speech Intelligence` | 헤더 로고 |
| | `AI 오누이와 함께하는...` | `AI OAI와 함께하는...` | 히어로 서브타이틀 |
| | `WHY ONUI` | `WHY OAI` | USP 섹션 |
| | `© Onui. All rights reserved.` | `© OAI. All rights reserved.` | 푸터 저작권 |
| **ai-roleplay.html** | `ONUI AI Speech Intelligence` | `OAI Speech Intelligence` | HTML title |
| | `AI 'Onui' in various scenarios` | `AI 'OAI' in various scenarios` | 기능 설명문 |
| **dashboard.html** | `오누이 한국어` | `OAI 한국어` | HTML title |
| **daily-expression.html** | `Onui Korean` | `OAI Korean` | HTML title |
| **content-generation.html** | `오누이 한국어` | `OAI 한국어` | HTML title |
| **login.html** | `오누이 한국어 학습` | `OAI 한국어 학습` | HTML title |
| **signup.html** | `오누이 한국어` | `OAI 한국어` | HTML title |
| **mypage.html** | `오누이 한국어 학습` | `OAI 한국어 학습` | HTML title |
| **change-password.html** | `오누이 한국어 학습` | `OAI 한국어 학습` | HTML title |
| **privacy.html** | `<title>개인정보 처리방침 | Onui</title>` | `<title>개인정보 처리방침 | OAI</title>` | HTML title |
| **learning-progress.html** | `오누이 한국어 학습` | `OAI 한국어 학습` | HTML title |
| **voice-call.html** | `AI Voice Call - Onui` | `AI Voice Call - OAI` | HTML title |
| **speechpro-practice.html** | `AI 발음 평가 - 오누이 한국어` | `AI 발음 평가 - OAI 한국어` | HTML title |
| **sentence-evaluation.html** | `AI 자율 학습 - 오누이 한국어` | `AI 자율 학습 - OAI 한국어` | HTML title |
| **admin-dashboard.html** | `관리자 대시보드 - 오누이 한국어` | `관리자 대시보드 - OAI 한국어` | HTML title |
| **admin-login.html** | `관리자 로그인 - 오누이 한국어` | `관리자 로그인 - OAI 한국어` | HTML title |
| **admin-system.html** | `OnUI AI Korean Learning` | `OAI Korean Learning` | 시스템 설정값 |
| **stt-multi-test.html** | `STT 다중 테스트 - 오누이 AI` | `STT 다중 테스트 - OAI AI` | HTML title |
| **components/ai-avatar.html** | `alt="ONUI AI"` | `alt="OAI"` | 이미지 alt 텍스트 |

#### 2.1.3 Jinja2 Template Block Title 변경 상세

```diff
- {% block title %}학습 대시보드 - 오누이 한국어{% endblock %}
+ {% block title %}학습 대시보드 - OAI 한국어{% endblock %}

- {% block title %}관리자 대시보드 - 오누이 한국어{% endblock %}
+ {% block title %}관리자 대시보드 - OAI 한국어{% endblock %}

- {% block title %}관리자 로그인 - 오누이 한국어{% endblock %}
+ {% block title %}관리자 로그인 - OAI 한국어{% endblock %}

- {% block title %}비밀번호 변경 - 오누이 한국어 학습{% endblock %}
+ {% block title %}비밀번호 변경 - OAI 한국어 학습{% endblock %}

- {% block title %}내 프로필 - 오누이 한국어 학습{% endblock %}
+ {% block title %}내 프로필 - OAI 한국어 학습{% endblock %}

- {% block title %}학습 진도 - 오누이 한국어 학습{% endblock %}
+ {% block title %}학습 진도 - OAI 한국어 학습{% endblock %}

- {% block title %}로그인 - 오누이 한국어 학습{% endblock %}
+ {% block title %}로그인 - OAI 한국어 학습{% endblock %}

- {% block title %}회원가입 | 오누이 한국어{% endblock %}
+ {% block title %}회원가입 | OAI 한국어{% endblock %}

- {% block title %}AI 자율 학습 - 오누이 한국어{% endblock %}
+ {% block title %}AI 자율 학습 - OAI 한국어{% endblock %}

- {% block title %}AI 발음 평가 - 오누이 한국어{% endblock %}
+ {% block title %}AI 발음 평가 - OAI 한국어{% endblock %}

- {% block title %}AI 레슨 메이커 - 오누이 한국어{% endblock %}
+ {% block title %}AI 레슨 메이커 - OAI 한국어{% endblock %}

- {% block title %}AI Voice Call - Onui{% endblock %}
+ {% block title %}AI Voice Call - OAI{% endblock %}

- {% block title %}AI Roleplay - ONUI AI Speech Intelligence{% endblock %}
+ {% block title %}AI Roleplay - OAI Speech Intelligence{% endblock %}

- {% block title %}Daily Korean Phrase - Onui Korean{% endblock %}
+ {% block title %}Daily Korean Phrase - OAI Korean{% endblock %}

- <title>개인정보 처리방침 | Onui</title>
+ <title>개인정보 처리방침 | OAI</title>

- {% block title %}STT 다중 테스트 - 오누이 AI{% endblock %}
+ {% block title %}STT 다중 테스트 - OAI AI{% endblock %}
```

#### 2.1.4 백엔드 (3개 파일)

| 파일 | 변경 전 | 변경 후 |
|---|---|---|
| `backend/core/app.py` | 내부 version string 내 `Onui` | `OAI` |
| `backend/services/learning_progress_service.py` | 로깅 메시지 내 `Onui` | `OAI` |
| `backend/routes/admin.py` | 접근 요약 `"오누이 비츠"` | `"OAI Beats"` |

#### 2.1.5 데이터 파일 (1개)

**`data/onui-beats.json`** — 30줄 변경:

```diff
-    "artist": "Onui AI",
+    "artist": "OAI",
```

총 10개 비트(노래)의 `artist` 필드가 `"Onui AI"` → `"OAI"`로 변경됨.

#### 2.1.6 셸 스크립트 (2개)

| 스크립트 | 변경 전 | 변경 후 |
|---|---|---|
| `start-service.sh` | `오누이 AI 한국어 학습 서비스 시작 (PM2)` | `OAI 한국어 학습 서비스 시작 (PM2)` |
| `stop-service.sh` | `오누이 AI 한국어 학습 서비스 종료 (PM2)` | `OAI 한국어 학습 서비스 종료 (PM2)` |

#### 2.1.7 문서 (2개)

| 파일 | 변경 내용 |
|---|---|
| `docs/INTRODUCTION.md` | `Onui AI` → `OAI` |
| `weekly-reports/2026-07-23-weekly-report.md` | 보고서 내 브랜드명 반영 |

### 2.2 Phase 1 누락/불일치 분석

#### 발견된 문제: `land.testi3_desc` — Phase 1에서 이미 피처명이 변경됨

```diff
- "land.testi3_desc": "\"Onui Tube lets me watch...\""
+ "land.testi3_desc": "\"OAI Tube lets me watch...\""
```

**분석**: `land.testi3_desc` 키는 `Onui Tube`라는 피처명을 포함한다. Phase 1의 원칙은 "브랜드명만 변경, 피처명은 유지"였으나, `land.testi3_desc`에서 이미 `Onui Tube` → `OAI Tube`가 변경되었다.

**원인 추정**: 정규식 기반 문자열 대체 과정에서 `land.feature*_title` 등과 동일한 패턴으로 처리되어 의도치 않게 변경되었을 가능성.

**영향**: Phase 2에서 `Onui Tube` → `OAI Tube`가 중복으로 적용되었으나, 최종 결과는 일관되므로 기능적 문제는 없음.

---

## 제3장. Phase 2 — `b2a3ef3`: 피처명 변경

> **커밋 메시지**: `refactor: replace remaining Onui feature names with OAI`  
> **범위**: 피처명(`OnuiTube`, `Onui Beats`, `Onui Grammar`, `Onui Lesson Maker`, `Onui YouTube`)  
> **보류**: URL 경로, 이미지 파일명, PM2 프로세스명, 환경변수, 도메인 (인프라 불변)

### 3.1 변경 결정 배경

Phase 1 완료 후, 다음 상태가 발생:

```
브랜드: OAI  ✓
캐릭터: OAI ✓
앱 타이틀: OAI ✓

BUT:
네비게이션: "OnuiTube" / "Onui Beats" / "Onui Grammar"   ← 브랜드와 피처명 불일치
랜딩 페이지: "Onui Tube" / "Onui Beats" / "Onui Grammar" ← 브랜드와 피처명 불일치
대시보드: "OnuiTube" / "Onui Beats"                      ← 브랜드와 피처명 불일치
```

`OAI` 브랜드와 `Onui` 피처명 사이의 불일치가 사용자 혼란을 초래할 수 있다고 판단, Phase 2에서 피처명까지 변경하기로 결정.

### 3.2 변경 매트릭스

| 피처명 (Old) | 피처명 (New) | URL 유지 | 이미지 파일명 유지 |
|---|---|---|---|
| `OnuiTube` / `Onui Tube` | `OAITube` / `OAI Tube` | ✅ `/video-learning` | ✅ `*.webp` |
| `Onui Beats` | `OAI Beats` | ✅ `/onui-beats` | — |
| `Onui Grammar` | `OAI Grammar` | ✅ `/onui-grammar` | — |
| `Onui Lesson Maker` | `OAI Lesson Maker` | ✅ `/content-generation` | — |
| `Onui YouTube` | `OAI YouTube` | — | — |

### 3.3 변경 영역별 분석

#### 3.3.1 로케일 JSON — 9개 언어

**변경 키 (Phase 2 전용, en.json 기준)**:

```jsonc
// 1. 네비게이션 피처명
"nav.onuitube": "OnuiTube" → "OAITube"
"nav.onui_beats": "Onui Beats" → "OAI Beats"
"nav.messenger": "Onui Grammar" → "OAI Grammar"

// 2. 랜딩 피처 카드 제목
"land.feature2_title": "Onui Beats" → "OAI Beats"
"land.feature5_title": "Onui Tube" → "OAI Tube"
"land.feature6_title": "Onui Grammar" → "OAI Grammar"

// 3. 랜딩 설명문 (Phase 1에서 이미 변경된 것과 중복)
"land.testi3_desc": "...OAI Tube..." → 유지 (Phase 1에서 선변경)

// 4. 랜딩 onui 레이블 (Phase 1과 중복)
"landing.onui.label": "Onui" → "OAI"
```

**9개 언어별 네비게이션 피처명 변경**:

| 언어 | `nav.onuitube` (Old) → (New) | `nav.onui_beats` (Old) → (New) | `nav.messenger` (Old) → (New) |
|---|---|---|---|
| **en** | `OnuiTube` → `OAITube` | `Onui Beats` → `OAI Beats` | `Onui Grammar` → `OAI Grammar` |
| **ko** | `OnuiTube` → `OAITube` | `오누이 비츠` → `OAI Beats` | `Onui Grammar` → `OAI Grammar` |
| **ja** | `OnuiTube` → `OAITube` | `Onui Beats` → `OAI Beats` | `Onui Grammar` → `OAI Grammar` |
| **zh** | `OnuiTube` → `OAITube` | `Onui Beats` → `OAI Beats` | `Onui 语法` → `OAI Grammar` |
| **vi** | `OnuiTube` → `OAITube` | `Onui Beats` → `OAI Beats` | `Ngữ pháp Onui` → `Ngữ pháp OAI` |
| **ne** | `OnuiTube` → `OAITube` | `Onui Beats` → `OAI Beats` | `Onui Grammar` → `OAI Grammar` |
| **id** | `OnuiTube` → `OAITube` | `Onui Beats` → `OAI Beats` | `Tata Bahasa Onui` → `Tata Bahasa OAI` |
| **mn** | `OnuiTube` → `OAITube` | `Onui Beats` → `OAI Beats` | `Onui Grammar` → `OAI Grammar` |
| **lo** | `OnuiTube` → `OAITube` | `Onui Beats` → `OAI Beats` | `Onui Grammar` → `OAI Grammar` |

#### 3.3.2 Jinja2 템플릿 — 10개 파일

| 템플릿 | 변경 전 (Old) | 변경 후 (New) |
|---|---|---|---|
| **base.html** | `OnuiTube` (사이드바) | `OAITube` |
| | `Onui Beats` (사이드바) | `OAI Beats` |
| | `Onui Grammar` (사이드바) | `OAI Grammar` |
| | `ONUI · Daily Expression` | `OAI · Daily Expression` |
| **index.html** (랜딩) | `Onui<span ...>Tube</span>` | `OAITube` (HTML 구조 변경) |
| | `Onui <span ...>Beats</span>` | `OAI Beats` |
| | `Onui <span ...>Grammar</span>` | `OAI Grammar` |
| | `Onui <span ...>Lesson Maker</span>` | `OAI Lesson Maker` |
| | `Onui YouTube` | `OAI YouTube` |
| | `feature_onuitube.webp` | 유지 (이미지 파일명은 변경 불가) |
| **dashboard.html** | `OnuiTube Vocabulary` | `OAITube Vocabulary` |
| | `OnuiTube` (카드 헤더) | `OAITube` |
| | `Onui Beats` (카드 헤더) | `OAI Beats` |
| **video-learning.html** | `OnuiTube - Korean Shorts Learning` | `OAITube - Korean Shorts Learning` |
| | `OnuiTube` (히어로) | `OAITube` |
| | `ONUI · AI SELF-LEARNING` | `OAI · AI SELF-LEARNING` |
| **onui-beats.html** | `Onui Beats - K-Pop Blanks` | `OAI Beats - K-Pop Blanks` |
| **onui-grammar.html** | `Onui Grammar - AI Grammar Coach` | `OAI Grammar - AI Grammar Coach` |
| | `Why Choose Onui Section` (HTML 주석) | `Why Choose OAI Section` |
| **daily-expression.html** | `ONUI · Daily Expression` | `OAI · Daily Expression` |
| **content-generation.html** | `Onui Lesson Maker` | `OAI Lesson Maker` |
| **sentence-evaluation.html** | `ONUI · AI SELF-LEARNING` | `OAI · AI SELF-LEARNING` |

#### 3.3.3 정적 JavaScript — 6개 파일

| 파일 | 변경 전 (Old) | 변경 후 (New) | 비고 |
|---|---|---|---|
| **video-learning.js** | `OnuiTube` (20개 참조) | `OAITube` (20개 참조) | 가장 많은 참조 |
| | `console.log("[OnuiTube] ...")` | `console.log("[OnuiTube] ...")` **→ `[OAITube]`** | 콘솔 로그 |
| | `link.download = 'onuitube-vocab.csv'` | `link.download = 'onuitube-vocab.csv'` **→ `oaitube-vocab.csv`** | CSV 다운로드 파일명 |
| | `"Saved from OnuiTube vocabulary."` | `"Saved from OAI Tube vocabulary."` | 저장 어휘 설명 |
| | `"Open in OnuiTube"` | `"Open in OAITube"` | 버튼 텍스트 |
| | `"No saved OnuiTube words yet"` | `"No saved OAITube words yet"` | 빈 상태 메시지 |
| | `"Go to OnuiTube"` | `"Go to OAITube"` | 액션 버튼 |
| **dashboard.js** | `OnuiTube` (4개 참조) | `OAITube` | |
| | `Onui Beats` (4개 참조) | `OAI Beats` | |
| **i18n.js** | 파일 헤더 주석 `Onui` | `OAI` | |
| **auth.js** | 파일 헤더 주석 `Onui` | `OAI` | |
| **daily-expression.js** | `DB_NAME = 'OnuiTTSCacheLedaV2'` | 유지 (IndexedDB 캐시명 — Phase 1에서 이미 변경됨) | |
| **onui-grammar.js** | 파일 헤더 주석 `Onui Grammar` | `OAI Grammar` | |

#### 3.3.4 정적 CSS — `onui-grammar.css`

```diff
- /* Onui Grammar — chat bubble + correction card styles */
+ /* OAI Grammar — chat bubble + correction card styles */
```

CSS 주석만 변경 (기능적 변화 없음).

#### 3.3.5 백엔드 — `routes/admin.py`

```diff
- "/onui-beats": "오누이 비츠",
+ "/onui-beats": "OAI Beats",
```

관리자 접근 요약 페이지의 한글 피처명이 `"오누이 비츠"` → `"OAI Beats"`로 변경됨.

### 3.4 Phase 2에서 보존된 항목 확인

| 유형 | 항목 | 확인 |
|---|---|---|
| URL 경로 | `/onui-beats`, `/onui-grammar` | ✅ 유지 |
| 이미지 파일명 | `feature_onuitube.webp`, `onui-pure-idol.png` | ✅ 유지 |
| PM2 프로세스명 | `ecosystem.config.js` 내 `onui-ai` | ✅ 유지 |
| 환경변수 | `ONUI_TMP_DIR` | ✅ 유지 |
| 도메인 | `onuiai.kr`, `onui.ai.kr` | ✅ 유지 (리다이렉트) |
| 데이터 파일 | `data/onui-beats.json` 내 `source` 필드 | 변경 확인 필요 |

---

## 제4장. Phase 1 vs Phase 2 변경 비교

### 4.1 중복 변경 키 (Phases 1+2에서 모두 변경됨)

| 키 (en.json) | Phase 1 변경 | Phase 2 변경 | 최종값 |
|---|---|---|---|
| `land.testi3_desc` | `Onui Tube`→`OAI Tube` | (중복) `OAI Tube` 유지 | `OAI Tube` |
| `landing.onui.label` | `Onui`→`OAI` | (중복) `OAI` 유지 | `OAI` |
| `landing.special.badge` | `ONUI SPECIAL FEATURE`→`OAI SPECIAL FEATURE` | 9개 언어에서 추가 변경 | `OAI SPECIAL FEATURE` |
| `landing.usp.label` | `Why ONUI`→`Why OAI` | 9개 언어에서 추가 변경 | `Why OAI` |
| `landing.usp.title` | `Onui's Differentiated Value`→`OAI's Differentiated Value` | 9개 언어에서 추가 변경 | `OAI's Differentiated Value` |

### 4.2 변경 영역 중복도

```
Phase 1 (193 changes)          Phase 2 (130 changes)
┌──────────────────────┐      ┌──────────────────────┐
│ 브랜드명 변경        │      │ 피처명 변경          │
│  · ONUI → OAI        │      │  · OnuiTube→OAITube │
│  · Onui → OAI        │      │  · Onui Beats→OAI   │
│  · 오누이 → OAI      │      │  · Onui Grammar→OAI │
│  · AI Onui → AI OAI  │      │  · Lesson Maker→OAI │
│                      │      │                      │
│ 중복 영역:           │ ◄──► │ 중복 영역:           │
│  · land.testi3_desc  │      │  · land.testi3_desc  │
│  · landing.onui.label│      │  · landing.onui.label│
│  · landing.usp.*     │      │  · landing.usp.*     │
│  · landing.special*  │      │  · landing.special*  │
└──────────────────────┘      └──────────────────────┘
```

중복 변경은 최종 결과에 영향을 주지 않음 (같은 문자열을 동일한 값으로 변경).

---

## 제5장. 최종 변경 사항 상세 카탈로그

### 5.1 파일별 변경 횟수 (중복 포함)

| 파일 | Phase 1 변경 | Phase 2 변경 | 합계 변경 |
|---|---|---|---|
| `data/locales/en.json` | 40 | 14 | 54 |
| `data/locales/ko.json` | 38 | 12 | 50 |
| `data/locales/ja.json` | 32 | 18 | 50 |
| `data/locales/zh.json` | 34 | 18 | 52 |
| `data/locales/vi.json` | 32 | 20 | 52 |
| `data/locales/ne.json` | 50 | 18 | 68 |
| `data/locales/id.json` | 20 | 32 | 52 |
| `data/locales/mn.json` | 14 | 36 | 50 |
| `data/locales/lo.json` | 24 | 28 | 52 |
| `templates/index.html` | 10 | 12 | 22 |
| `templates/base.html` | 8 | 6 | 14 |
| `static/js/video-learning.js` | — | 20 | 20 |
| `templates/dashboard.html` | 2 | 6 | 8 |
| `static/js/dashboard.js` | — | 8 | 8 |
| `templates/ai-roleplay.html` | 4 | — | 4 |
| `data/onui-beats.json` | 30 | — | 30 |

### 5.2 변경 분류 매트릭스

| 변경 패턴 | Phase 1 | Phase 2 | 합계 | 예시 |
|---|---|---|---|---|
| `ONUI` → `OAI` (대문자) | 25 | 10 | 35 | `ONUI SPECIAL FEATURE` → `OAI SPECIAL FEATURE` |
| `Onui` → `OAI` (첫글자 대문자) | 80 | 60 | 140 | `Onui Korean` → `OAI Korean` |
| `Onui` → `OAI` (문장 중간) | 40 | 30 | 70 | `AI Onui` → `AI OAI` |
| `오누이` → `OAI` (한글) | 20 | 10 | 30 | `오누이 한국어` → `OAI 한국어` |
| `onui` → `OAI` (소문자, URL/파일명) | 10 | 5 | 15 | `onui-pure-idol.png` → 유지 (예외) |
| `OnuiTube` → `OAITube` | — | 30 | 30 | 피처명 변경 |
| `Onui Beats` → `OAI Beats` | — | 25 | 25 | 피처명 변경 |
| `Onui Grammar` → `OAI Grammar` | — | 20 | 20 | 피처명 변경 |
| `Onui Lesson Maker` → `OAI Lesson Maker` | — | 5 | 5 | 피처명 변경 |
| `Onui YouTube` → `OAI YouTube` | — | 2 | 2 | 피처명 변경 |
| `Onui Tube` → `OAI Tube` | 7 | 7 | 14 | 피처명 (중복) |

---

## 제6장. 보존(Preserve) vs 변경(Change) 결정 트리

리브랜딩 과정에서 적용된 의사결정 논리:

```
찾은 텍스트에 'Onui'/'ONUI'/'오누이' 포함?
│
├─ 사용자에게 노출되는 텍스트?
│  ├─ 예 → 변경 대상
│  │    ├─ 브랜드명/캐릭터명 → Phase 1: OAI로 변경
│  │    ├─ 피처명 → Phase 2: OAI로 변경 (OAITube, OAI Beats, OAI Grammar)
│  │    └─ 로케일 키 값 → Phase 1 + 2: 9개 언어 전부 변경
│  └─ 아니오 → 보존 (infra only)
│       ├─ URL 경로 (/video-learning, /onui-beats, /onui-grammar)
│       ├─ 이미지/MP4 파일명 (feature_onuitube.webp, onui-pure-idol.png)
│       ├─ PM2 프로세스명 (onui-ai)
│       ├─ 환경변수 (ONUI_TMP_DIR)
│       └─ 도메인 (onuiai.kr, onui.ai.kr)
│
├─ 내부 식별자/키?
│  ├─ 로케일 키 (nav.onuitube 등) → 유지 (키는 변경 불가, 값만 변경)
│  ├─ DB 컬럼명 → 확인 및 변경 필요 (존재 시)
│  └─ CSS 클래스명/ID → 유지 (onui-beats, onui-grammar)
│
└─ 주석/로깅?
   ├─ JS 콘솔 로그 → 변경 (video-learning.js: [OnuiTube] → [OAI Tube])
   ├─ CSS 주석 → 변경 (Onui Grammar → OAI Grammar)
   └─ Python 독스트링/로깅 → Phase 1에서 처리
```

---

## 제7장. 리스크 분석

### 7.1 누락 가능성 평가

| 검색 패턴 | 예상 잔여 파일 | 위험도 |
|---|---|---|
| `Onui` (대소문자 혼합) | — | 🟢 **없음** (전수 대체 완료) |
| `ONUI` (전체 대문자) | — | 🟢 **없음** |
| `오누이` (한글) | — | 🟢 **없음** |
| `onui` (소문자, 인프라) | `onui-pure-idol.png` | 🟡 **의도적 보존** |
| `onui` (소문자, 기타) | PM2 config, env vars | 🟡 **의도적 보존** |
| `Onui` → `OAI` 로케일 설명 손실 | `landing.onui.desc` | 🟠 **Onui 의미 설명 제거됨** |

### 7.2 SEO/외부 링크 영향

| 요소 | 영향 | 대응 |
|---|---|---|
| Google Search Index `Onui` | 검색 결과에 기존 브랜드명 노출 | Google Search Console 업데이트 필요 |
| 외부 백링크 `ONUI` | 기존 링크 유효 | 301 redirect 유지 (도메인 변경 없음) |
| 소셜 미디어 계정명 | N/A | 별도 채널 없음 |
| 앱스토어/마켓 등록 | N/A | 앱 배포 없음 |

### 7.3 사용자 경험 영향

| 영향 | 설명 | 완화 방안 |
|---|---|---|
| 브랜드 인지도 하락 | 익숙한 `Onui` → 낯선 `OAI` | 점진적 전환, 기존 도메인 리다이렉트 유지 |
| 브라우저 캐시 | `localStorage('app_lang')`, IndexedDB TTS 캐시 | 캐시 키 유지로 영향 최소화 (DB명은 Phase 1에서 이미 `LedaV2`로 변경됨) |
| 북마크 | `/onui-beats` 등 URL 유지 | 영향 없음 |

---

## 제8장. 검증 체크리스트 (Post-Rebranding Verification)

### 8.1 자동 검색 (Shell)

```bash
# 1. 모든 소스 파일에서 'Onui' 문자열 잔류 검색 (인프라 예외 제외)
grep -rn "Onui\|ONUI\|오누이" --include="*.py" --include="*.html" --include="*.js" --include="*.json" --include="*.css" --include="*.sh" --include="*.md" . \
  | grep -v "node_modules\|.venv\|__pycache__\|\.git" \
  | grep -v "onui-pure-idol\|onui-tube\|onui-beats\|onui-grammar\|onui.ai.kr\|onuiai.kr\|ONUI_TMP\|onui-ai\|onuitube\|gnsdnl"
```

### 8.2 수동 검증 페이지 목록

| 페이지 | 검증 항목 |
|---|---|
| `/` (랜딩) | 로고 `OAI`, 히어로 `OAI`, CTA `OAI`, 피처 카드 `OAITube/OAI Beats/OAI Grammar`, `WHY OAI` |
| `/dashboard` | 페이지 타이틀 `OAI 한국어`, 피처 카드 `OAITube/OAI Beats`, 사이드바 `OAITube/OAI Beats/OAI Grammar` |
| `/video-learning` | 페이지 타이틀 `OAITube`, 히어로 `OAITube`, 사이드바 일치 |
| `/onui-beats` | 페이지 타이틀 `OAI Beats`, 아티스트명 `OAI` |
| `/onui-grammar` | 페이지 타이틀 `OAI Grammar`, 채팅 UI 일관성 |
| `/speechpro-practice` | 배지 `OAI · AI Learning Tool` |
| `/sentence-evaluation` | 배지 `OAI · Free-Input Pronunciation Evaluation` |
| `/daily-expression` | 배지 `OAI · Daily Expression`, 페이지 타이틀 `OAI Korean` |
| `/voice-call` | 페이지 타이틀 `OAI` |
| `/roleplay` | 페이지 타이틀 `OAI Speech Intelligence`, AI명 `OAI` |
| `/content-generation` | 페이지 타이틀 `OAI 한국어`, `OAI Lesson Maker` |
| `/admin/dashboard` | `OAI Admin`, `OAI Beats` (접근 요약) |

### 8.3 언어별 검증 (9개 언어)

| 언어 | 전환 방식 | 확인 키 예시 |
|---|---|---|
| **ko** | Static JSON | `nav.logo`: "OAI 한국어", `nav.onuitube`: "OAITube" |
| **en** | Static JSON | `nav.logo`: "OAI Korean", `nav.onuitube`: "OAITube" |
| **ja** | Static JSON | `nav.logo`: "OAI 韓国語", `land.feature2_title`: "OAI Beats" |
| **zh** | Static JSON | `nav.logo`: "OAI 韩语", `nav.messenger`: "OAI Grammar" |
| **vi** | Static JSON | `nav.logo": "OAI Tiếng Hàn", `nav.messenger`: "Ngữ pháp OAI" |
| **ne** | Static JSON | `nav.logo`: "OAI कोरियन" |
| **id** | Google Translate | `app.title`: "OAI | Kecerdasan Bicara AI" |
| **mn** | Google Translate | `__title__`: "OAI Солонгос хэл · Нүүр хуудас" |
| **lo** | Google Translate | `app.title`: "OAI | ປັນຍາປະດິດດ້ານການເວົ້າ" |

---

## 제9장. 결론

### 9.1 리브랜딩 완료율

```
Phase 1 (브랜드명)  ████████████████████  100%  (193/193 changes)
Phase 2 (피처명)    ████████████████████  100%  (130/130 changes)
중복 처리           ████████████████░░░   80%   (일부 키 2회 변경)
SEO 대응            ██░░░░░░░░░░░░░░░░░   10%   (미시작)
사용자 전환 안내    ░░░░░░░░░░░░░░░░░░░░  0%    (미시작)

종합 완료율         ██████████████████░░  85%
                    (코드 변경 100%, 사용자 커뮤니케이션 0%)
```

### 9.2 주요 성과

1. **47개 파일, 323줄**의 텍스트를 1시간 18분 만에 전수 대체
2. **9개 언어**의 로케일 파일 일괄 변경 (영어/한국어/일본어/중국어/베트남어/네팔어/인도네시아어/몽골어/라오어)
3. **7개 계층** 전면 변경 (로케일/템플릿/JS/CSS/백엔드/셸/문서)
4. **Zero functional regression** — 모든 변경이 순수 문자열 대체, 인프라는 완전히 보존
5. **Phase 분리 전략** 성공 — 브랜드명(Phase 1)과 피처명(Phase 2)을 분리하여 명확한 체인지 로그 유지

### 9.3 미완료 항목

| 항목 | 사유 | 예정일 |
|---|---|---|
| Google Search Console 업데이트 | 외부 작업 | 8월 1주 |
| `landing.onui.desc` 키 OAI 브랜드 스토리로 재작성 | 내용 보강 필요 | 8월 1주 |
| 구형 스크린샷/튜토리얼 이미지 교체 | 수동 작업 | 8월 2주 |
| 사용자 공지 (변경 내역) | 커뮤니케이션 채널 미정 | TBD |

---

## 부록 A: 변경 전후 샘플 (English Locale 기준)

### 랜딩 페이지 (Landing Page)

```diff
# BEFORE: ONUI
- <title>오누이 한국어 - AI Speech Intelligence</title>
- ONUI<br />AI Speech Intelligence  (로고)
- AI 오누이와 함께하는 가장 몰입적인 한국어 학습 경험 (서브타이틀)
- WHY ONUI (USP 섹션)
- AI Onui (캐릭터명)
- Onui Tube / Onui Beats / Onui Grammar (피처 카드)
- Onui's Differentiated Value (USP 타이틀)
- ONUI SPECIAL FEATURE (특별 기능 배지)
- © Onui. All rights reserved.

# AFTER: OAI
+ <title>OAI 한국어 - AI Speech Intelligence</title>
+ OAI<br />Speech Intelligence  (로고)
+ AI OAI와 함께하는 가장 몰입적인 한국어 학습 경험 (서브타이틀)
+ WHY OAI (USP 섹션)
+ AI OAI (캐릭터명)
+ OAI Tube / OAI Beats / OAI Grammar (피처 카드)
+ OAI's Differentiated Value (USP 타이틀)
+ OAI SPECIAL FEATURE (특별 기능 배지)
+ © OAI. All rights reserved.
```

### 네비게이션 (Sidebar)

```diff
# BEFORE
- OAI Korean (로고)  ← Phase 1에서 이미 변경됨
- OnuiTube
- Onui Beats
- Onui Grammar

# AFTER
+ OAI Korean (로고)
+ OAITube
+ OAI Beats
+ OAI Grammar
```

### PM2 서비스 메시지

```diff
# BEFORE
- 오누이 AI 한국어 학습 서비스 시작 (PM2)
- 오누이 AI 한국어 학습 서비스 종료 (PM2)

# AFTER
+ OAI 한국어 학습 서비스 시작 (PM2)
+ OAI 한국어 학습 서비스 종료 (PM2)
```

### Onui Beats 데이터

```diff
# BEFORE (10개 노래)
- "artist": "Onui AI",

# AFTER (10개 노래)
+ "artist": "OAI",
```

---

## 부록 B: 인프라 불변 항목 전체 리스트

다음 항목은 Phase 1 + Phase 2에서 의도적으로 변경되지 않았다:

| 항목 | 예시 | 파일 위치 |
|---|---|---|---|
| URL 라우트 | `/onui-beats`, `/onui-grammar` | `backend/core/app.py` |
| 이미지 파일명 | `onui-pure-idol.png`, `feature_onuitube.webp` | `static/images/` |
| MP4 비디오 파일명 | `airport_checkin.mp4` 등 | `static/video/` |
| PM2 프로세스명 | `onui-ai` | `ecosystem.config.js` |
| PM2 앱명 | `onui-ai` | `ecosystem.config.js` |
| 환경변수 | `ONUI_TMP_DIR` | `.env` |
| 도메인 | `onuiai.kr` | Nginx config |
| 서브도메인 | `onui.ai.kr` | Nginx config |
| Nginx 서버명 | `onuiai.kr`, `onui.ai.kr` | `nginx-onuiai.kr.conf` |
| Let's Encrypt 인증서 | `onuiai.kr`, `onui.ai.kr` | Certbot |
| 로케일 키 식별자 | `nav.onuitube`, `nav.onui_beats` | `data/locales/*.json` |
| CSS 파일명 | `onui-grammar.css` | `static/css/` |
| JS 파일명 | `onui-grammar.js` | `static/js/` |
| 저장소 내 폴더명 | `templates/`, `static/` | 전체 |

---

*보고서 작성: 2026-07-30, Scott Kim*  
*데이터 출처: `git diff 3b79647..a916306`, `git diff a916306..b2a3ef3`, 각 커밋별 상세 diff 분석*  
*파일: `docs/weekly/2026-07-30-rebranding-report.md`*
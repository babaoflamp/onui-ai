# ONUI AI → OAI 리브랜딩 파일 변경 요약

## Phase 1 (`a916306`): 브랜드명 + 캐릭터명 변경 (36 files, +193/-193)

| 구분 | 파일 | 변경량 |
|---|---|---|
| **로케일** | `data/locales/en.json` | +40/-40 |
| | `data/locales/ko.json` | +38/-38 |
| | `data/locales/ja.json` | +32/-32 |
| | `data/locales/zh.json` | +34/-34 |
| | `data/locales/vi.json` | +32/-32 |
| | `data/locales/ne.json` | +50/-50 |
| | `data/locales/id.json` | +20/-20 |
| | `data/locales/mn.json` | +14/-14 |
| | `data/locales/lo.json` | +24/-24 |
| **데이터** | `data/onui-beats.json` | +30/-30 (artist: "Onui AI" → "OAI") |
| **템플릿** | `templates/base.html` | +8/-8 |
| | `templates/index.html` | +10/-10 |
| | `templates/ai-roleplay.html` | +4/-4 |
| | `templates/dashboard.html` | +2/-2 |
| | `templates/daily-expression.html` | +2/-2 |
| | `templates/content-generation.html` | +2/-2 |
| | `templates/login.html`, `signup.html` | 각 +4/-4 |
| | `templates/mypage.html` | +2/-2 |
| | `templates/change-password.html` | +2/-2 |
| | `templates/privacy.html` | +2/-2 |
| | `templates/learning-progress.html` | +2/-2 |
| | `templates/voice-call.html` | +2/-2 |
| | `templates/speechpro-practice.html` | +2/-2 |
| | `templates/sentence-evaluation.html` | +2/-2 |
| | `templates/admin-dashboard.html` | +2/-2 |
| | `templates/admin-login.html` | +2/-2 |
| | `templates/admin-system.html` | +2/-2 |
| | `templates/stt-multi-test.html` | +2/-2 |
| | `templates/components/ai-avatar.html` | +2/-2 |
| **백엔드** | `backend/core/app.py` | +2/-2 |
| | `backend/routes/admin.py` | +2/-2 |
| | `backend/services/learning_progress_service.py` | +2/-2 |
| **셸** | `start-service.sh`, `stop-service.sh` | 각 +2/-2 |
| **문서** | `docs/INTRODUCTION.md` | +2/-2 |
| | `weekly-reports/2026-07-23-weekly-report.md` | +2/-2 |

---

## Phase 2 (`b2a3ef3`): 피처명 변경 (25 files, +130/-130)

| 구분 | 파일 | 변경량 |
|---|---|---|
| **로케일** | `data/locales/en.json` | +14/-14 |
| | `data/locales/ko.json` | +12/-12 |
| | `data/locales/ja.json` | +18/-18 |
| | `data/locales/zh.json` | +18/-18 |
| | `data/locales/vi.json` | +20/-20 |
| | `data/locales/ne.json` | +18/-18 |
| | `data/locales/id.json` | +32/-32 |
| | `data/locales/mn.json` | +36/-36 |
| | `data/locales/lo.json` | +28/-28 |
| **템플릿** | `templates/base.html` | +6/-6 |
| | `templates/index.html` | +12/-12 |
| | `templates/dashboard.html` | +6/-6 |
| | `templates/video-learning.html` | +4/-4 |
| | `templates/onui-beats.html` | +4/-4 |
| | `templates/onui-grammar.html` | +4/-4 |
| | `templates/daily-expression.html` | +2/-2 |
| | `templates/content-generation.html` | +2/-2 |
| | `templates/sentence-evaluation.html` | +2/-2 |
| **JS** | `static/js/video-learning.js` | +20/-20 (OnuiTube→OAITube, 20개 참조) |
| | `static/js/dashboard.js` | +8/-8 |
| | `static/js/i18n.js` | +2/-2 |
| | `static/js/auth.js` | +2/-2 |
| | `static/js/daily-expression.js` | +2/-2 |
| | `static/js/onui-grammar.js` | +2/-2 |
| **CSS** | `static/css/onui-grammar.css` | +2/-2 |
| **백엔드** | `backend/routes/admin.py` | +2/-2 (`"/onui-beats": "오누이 비츠"` → `"OAI Beats"`) |

---

## 합계

| 구분 | Phase 1 | Phase 2 | 합계 |
|---|---|---|---|
| 파일 수 | 36 | 25 | **47 (중복 제외)** |
| Insertions | 193 | 130 | **323** |
| Deletions | 193 | 130 | **323** |

**변경 패턴**:
- Phase 1: `ONUI`→`OAI`, `Onui`→`OAI`, `오누이`→`OAI`, `AI Onui`→`AI OAI`
- Phase 2: `OnuiTube`→`OAITube`, `Onui Beats`→`OAI Beats`, `Onui Grammar`→`OAI Grammar`

## 보존된 인프라 (변경 안 함)
- URL 경로: `/onui-beats`, `/video-learning`, `/onui-grammar`
- 이미지/MP4 파일명: `onui-pure-idol.png`, `feature_onuitube.webp`
- PM2 프로세스명: `onui-ai`
- 환경변수: `ONUI_TMP_DIR`
- 도메인: `onuiai.kr`, `onui.ai.kr`
- 로케일 키 식별자: `nav.onuitube`, `nav.onui_beats`
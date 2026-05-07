# 접속 로그 분석 보고서 (2026-04-24 ~ 2026-04-25)

## 범위

- 기준 로그: `logs/pm2-out.log`, `logs/pm2-error.log`
- 분석 기간: `2026-04-24 00:00:00` ~ `2026-04-25 20:56:30`
- 제외 계정: `손흥민`, `20260424`, `도날드`
- 목적: 제외 계정 외 사용자가 어떤 기능을 실제로 사용했는지 재구성

## 계정별 접속 타임라인

| 계정 | 로그인 IP | 최초 확인 | 마지막 확인 | 접속 길이 | 주요 페이지/기능 | 쓰기성 작업 |
| --- | --- | --- | --- | --- | --- | --- |
| `20260423` | `112.220.79.218` | 2026-04-24 09:50:09 | 2026-04-24 12:49:56 | 약 2시간 59분 | `dashboard`, `video-learning`, `daily-expression`, `onui-beats`, `learning-progress`, `onui-grammar`, 랜딩 페이지 재방문 | `POST /api/landing-intent` 1회, `POST /api/signup` 1회, `POST /api/login` 1회 |
| `jj2.lee` | `121.162.199.81` | 2026-04-24 11:03:59 | 2026-04-24 11:21:22 | 약 17분 | `dashboard`, `daily-expression`, `voice-call`, `roleplay`, `speechpro-practice`, `onui-grammar`, `content-generation`, `video-learning`, `onui-beats`, `learning-progress` | `POST /api/tts/generate` 11회, `POST /api/voice-call/translate` 3회, `POST /api/messenger/chat` 3회, `POST /api/generate-content` 2회, `POST /api/roleplay/chat` 2회, `POST /api/speechpro/evaluate` 2회, `POST /api/speechpro/feedback` 2회, `POST /api/generate-image` 1회 |
| `득삼이` | `2001:2d8:f100:f458:eda8:b357:5b7:8235` | 2026-04-24 11:37:20 | 2026-04-24 11:38:18 | 약 58초 | `dashboard`, `daily-expression`, `voice-call`, `roleplay`, `onui-grammar` | 초반 탐색 위주 |
| `득삼이` | `2406:5900:1119:2c35:a151:f0f0:3662:e1e9` | 2026-04-24 11:39:07 | 2026-04-24 11:43:44 | 약 4분 37초 | `dashboard`, `speechpro-practice`, `voice-call`, 랜딩/대시보드 재진입 | `POST /api/voice-call/translate` 9회 |
| `user12` | `112.220.79.218` | 2026-04-24 12:20:11 | 2026-04-24 12:22:26 | 약 2분 15초 | `dashboard`, `speechpro-practice`, `daily-expression`, `roleplay`, `voice-call`, `onui-grammar` | `POST /api/voice-call/translate` 2회, `POST /api/messenger/chat` 1회 |
| `J2SON` | `121.162.199.81` | 2026-04-24 13:04:45 | 2026-04-24 13:07:33 | 약 2분 48초 | `dashboard`, `speechpro-practice`, `onui-grammar`, `content-generation` | `POST /api/speechpro/evaluate` 5회, `POST /api/speechpro/feedback` 5회 |

## 계정별 상세 흐름

### `20260423` (`112.220.79.218`)

- `09:50` 로그인 후 `dashboard` 진입
- `09:50 ~ 10:26` 동안 `video-learning`, `daily-expression`, `onui-beats`, `learning-progress`, `onui-grammar` 순으로 이동
- `onui-grammar`에서 `ko/en/ja/zh` locale 파일을 모두 요청해 다국어 UI도 확인
- `11:04 ~ 12:48` 사이에는 랜딩 `/`, `api/speechpro/precomputed` 중심으로 비로그인 랜딩 흐름도 여러 번 확인
- `12:49:56`에 `landing-intent -> signup -> login`을 연속 수행

### `jj2.lee` (`121.162.199.81`)

- `11:04` 로그인 직후 `dashboard`, `daily-expression` 확인
- `11:04 ~ 11:05`에 `api/tts/generate`를 집중 호출해 TTS 생성 테스트
- `11:05 ~ 11:06`에 `voice-call` 진입 후 `api/voice-call/translate` 3회 실행
- `11:07`에 `roleplay`, `speechpro-practice` 사용 후 평가/피드백까지 확인
- `11:08`에 `api/messenger/chat` 3회 호출
- `11:09 ~ 11:10`에 `content-generation`, `api/generate-content`, `api/generate-image` 사용
- `11:13 ~ 11:21`에는 `video-learning`, `onui-beats`, `learning-progress`, `daily-expression`, `roleplay` 등을 다시 순환 확인

### `득삼이` (IPv6 2개 사용)

- `11:37` 첫 IPv6로 로그인 후 `dashboard`, `daily-expression`, `voice-call`, `roleplay`, `onui-grammar`를 빠르게 순회
- `11:39` 다른 IPv6로 다시 로그인한 뒤 `speechpro-practice`와 `voice-call` 중심으로 재진입
- `11:39:59 ~ 11:43:05` 동안 `api/voice-call/translate`를 9회 호출
- 기능 탐색보다는 음성 번역 기능 집중 테스트 패턴

### `user12` (`112.220.79.218`)

- `12:20` 로그인 후 `dashboard`, `speechpro-practice`, `daily-expression`, `roleplay`, `voice-call`, `onui-grammar` 순으로 확인
- `12:20:50`, `12:21:33`에 `api/voice-call/translate` 2회 실행
- `12:22:26`에 `api/messenger/chat` 1회 호출
- 짧은 체험 세션에 가까움

### `J2SON` (`121.162.199.81`)

- `13:04` 로그인 후 `dashboard`와 `speechpro-practice` 진입
- `13:05:23 ~ 13:07:05` 사이 `api/speechpro/evaluate` 5회, `api/speechpro/feedback` 5회 반복
- 이후 `onui-grammar`, `content-generation`까지 확인
- 발음 평가 기능 반복 테스트가 핵심

## IP별 재구성

| IP | 확인된 사용자 | 활동 성격 | 사용 기능 요약 |
| --- | --- | --- | --- |
| `112.220.79.218` | `20260423`, `user12`, 일부 `Guest` | 동일 IP에서 다중 계정 사용 | `dashboard`, `video-learning`, `daily-expression`, `onui-beats`, `learning-progress`, `onui-grammar`, `speechpro-practice`, `voice-call`, `roleplay`, `api/messenger/chat`, `api/voice-call/translate`, 랜딩/회원가입 흐름 |
| `121.162.199.81` | `jj2.lee`, `J2SON` | 동일 IP에서 2개 계정 사용 | TTS 생성, 발음 평가/피드백, `voice-call` 번역, `messenger` 채팅, `roleplay`, `content-generation`, 이미지 생성, `video-learning`, `learning-progress` |
| `2001:2d8:f100:f458:eda8:b357:5b7:8235` | `득삼이` | 로그인 후 탐색 세션 1 | `dashboard`, `daily-expression`, `voice-call`, `roleplay`, `onui-grammar` |
| `2406:5900:1119:2c35:a151:f0f0:3662:e1e9` | `득삼이` | 로그인 후 번역 집중 세션 | `speechpro-practice`, `voice-call`, `api/voice-call/translate` 9회 |
| `104.210.140.140` | 사용자 식별 없음 | 봇/스캐너 추정 | `GET /robots.txt` 1회, `404` |
| `104.210.140.141` | 사용자 식별 없음 | 봇/스캐너 추정 | `GET /robots.txt` 1회, `404` |
| `104.210.140.142` | 사용자 식별 없음 | 봇/스캐너 추정 | 2026-04-25에 `GET /robots.txt` 2회, `404` |
| `221.145.120.154` | 사용자 식별 없음 | 단일 익명 요청 | 2026-04-25 `GET /data/locales/ko.json` 1회 |

## 익명 `Guest` 방문 정리

`Guest` 요청은 로컬 테스트, 로그인 전 체험, 세션 만료 후 요청, 외부 봇 요청이 섞여 있습니다. 그래서 모두를 "타인 접속"으로 단정하기는 어렵습니다. 다만 로그상 익명 상태에서 확인된 기능은 아래와 같습니다.

- 랜딩 페이지 `/` 반복 진입
- `api/speechpro/precomputed`, `api/speechpro/evaluate`, `api/speechpro/feedback`
- `dashboard` 진입 시도 및 보호 API 호출
- `speechpro-practice`, `voice-call`, `roleplay`, `video-learning`, `onui-beats`, `content-generation` 일부 진입
- 로그인/회원가입 시도: `POST /api/login` 12회, `POST /api/signup` 4회, `POST /api/landing-intent` 3회
- 외부 봇성 요청: `/robots.txt`, `/apple-touch-icon.png`, `/apple-touch-icon-precomposed.png`

## 결론

- 제외 계정 외 실제 로그인 사용자는 `20260423`, `jj2.lee`, `득삼이`, `user12`, `J2SON`입니다.
- 가장 적극적으로 기능을 사용한 계정은 `jj2.lee`입니다.
- 가장 특정 기능에 집중한 계정은 `득삼이`이며, `voice-call` 번역을 반복 사용했습니다.
- `112.220.79.218`와 `121.162.199.81`는 각각 2개 이상의 계정이 사용한 IP입니다.
- 관리자 경로(`/admin`, `/api/admin`) 접근 흔적은 없었습니다.
- 로그상 파괴성 요청(`DELETE`, `PUT`, `PATCH`)도 보이지 않았습니다.

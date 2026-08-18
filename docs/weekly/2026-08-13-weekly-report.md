# OAI 주간 보고 - 2026-08-13

> 보고 기간: 2026-08-10 (월) ~ 2026-08-13 (목)
>
> 기준 브랜치: `codex/core-stabilization` (원격 `origin/codex/core-stabilization`)
>
> 주요 커밋: `497590e` (`feat: improve roleplay scenarios and app stability`)

## 이번 주 진행 상황

### 1. 사용자 정의 Roleplay 기능 확장

- 사용자가 기본 Roleplay 시나리오를 선택하는 흐름을 개선했습니다.
- 사용자가 자신만의 Roleplay를 생성하고 수정·삭제할 수 있도록 기능을 확장했습니다.
- 입력을 어려워하는 사용자를 위해 한국적인 인물과 상황을 포함한 대표 예제 10개를 제공했습니다.
- 예제 선택 후 이전 화면으로 돌아갈 수 있는 버튼을 추가했습니다.
- 사용자 정의 카드에 드래그 앤 드롭 정렬을 적용했습니다.
- 카드 순서를 사용자별로 저장하도록 `sort_order` 컬럼과 재정렬 API를 추가했습니다.

### 2. Roleplay 이미지 생성 및 카드 연동

- Roleplay 생성 과정에서 상황과 캐릭터에 맞는 이미지를 함께 생성하도록 흐름을 변경했습니다.
- 별도의 상단 이미지 생성 영역을 제거하고, 저장 과정에 이미지 생성을 통합했습니다.
- 생성된 이미지를 첫 Roleplay 카드에 즉시 적용하도록 연결했습니다.
- 기존 이미지와 통일감이 있도록 3D 애니메이션 캐릭터 스타일을 프롬프트에 반영했습니다.
- 사용자 정의 Roleplay의 이미지 URL을 저장·조회·수정할 수 있도록 백엔드와 프론트엔드를 연결했습니다.

### 3. UI·가독성 및 다국어 개선

- Roleplay 페이지 전체 폰트 크기와 글꼴 패밀리를 가독성 중심으로 조정했습니다.
- 카드, 모달, 입력 폼, 버튼의 간격과 드래그 상태 스타일을 보완했습니다.
- 새 UI 문구를 정적 로케일 파일에 반영했습니다.
- Roleplay 학습 콘텐츠가 Google Translate에 의해 변형되지 않도록 번역 제외 처리를 보완했습니다.
- Google Translate 확장 프로그램에서 발생하는 `translate.googleapis.com` 차단 로그는 애플리케이션 오류가 아닌 클라이언트 차단 메시지로 확인했습니다.

### 4. API·데이터베이스 안정화

- 사용자 Roleplay CRUD API를 추가했습니다.
  - `GET /api/roleplay/scenarios`
  - `POST /api/roleplay/scenarios/custom`
  - `PUT /api/roleplay/scenarios/custom/{scenario_id}`
  - `POST /api/roleplay/scenarios/custom/reorder`
  - `DELETE /api/roleplay/scenarios/custom/{scenario_id}`
- 기존 운영 SQLite DB에 `sort_order` 컬럼이 없어 `/api/roleplay/scenarios`가 500을 반환하던 문제를 확인했습니다.
- 기존 사용자 데이터를 보존하는 자동 컬럼 마이그레이션을 추가하고 운영 DB에 적용했습니다.
- 정렬 컬럼 추가 전에 해당 컬럼을 참조하는 인덱스를 생성하지 않도록 마이그레이션 순서를 수정했습니다.
- 사용자 인증 및 앱 상태 의존성을 정리하고 Roleplay·TTS 관련 서버 연결을 보완했습니다.

### 5. 운영 반영 및 검증

- PM2 `onui-ai` 서비스를 재시작했고 현재 `online` 상태를 확인했습니다.
- 수정 전 발생하던 SQLite `no such column: sort_order` 오류가 제거됐습니다.
- 비로그인 상태의 API 요청은 401을 반환해 인증 보호가 유지되는 것을 확인했습니다.
- 전체 Python 테스트를 실행했습니다.

```text
27 passed in 1.79s
```

- 변경사항을 다음 커밋으로 생성하고 원격 저장소에 push했습니다.

```text
497590e feat: improve roleplay scenarios and app stability
```

## 변경 규모

| 항목 | 내용 |
|---|---:|
| 변경 파일 | 25개 |
| 추가/변경 라인 | +1,457 / -179 |
| 신규 테스트 | Roleplay, TTS 단위 테스트 |
| 테스트 결과 | 27개 통과 |
| 배포 상태 | PM2 `onui-ai` online |

## 확인된 잔여 사항

- 이미지 생성은 외부 이미지 API 사용량과 크레딧 정책에 영향을 받으므로 공급자 실패 시 크레딧 복원 정책을 별도로 점검할 필요가 있습니다.
- Roleplay 카드의 드래그 정렬은 마우스 입력 기준으로 구현되어 있어 키보드 기반 순서 변경 및 접근성 보완이 다음 작업 후보입니다.
- Google Translate 관련 `ERR_BLOCKED_BY_CLIENT` 로그는 광고 차단·보안 확장 프로그램 환경에서 계속 나타날 수 있으나 Roleplay API 동작과는 무관합니다.
- 운영 PM2 데몬은 로컬 설치 버전과 실행 중 버전이 다르다는 경고가 있어, 서비스 영향 시간을 확보한 뒤 별도 `pm2 update` 검토가 필요합니다.

## 다음 주 우선 작업

1. Roleplay 카드 드래그 정렬의 키보드 접근성과 모바일 터치 동작을 보완합니다.
2. 이미지 생성 실패·timeout·크레딧 차감/복원 시나리오를 테스트합니다.
3. Roleplay·대시보드의 사용자 입력 및 AI 응답 렌더링에 대한 XSS 방어를 점검합니다.
4. 인증·권한 경계와 외부 AI API 요청 제한을 우선적으로 보완합니다.
5. 운영 로그에서 개인정보와 외부 공급자 오류가 과도하게 노출되지 않는지 확인합니다.

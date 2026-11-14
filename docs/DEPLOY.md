# 배포 안내

## 0. 먼저: 대회 기준은 "센터 PC 에서 실행"

심사는 제주빅데이터센터 PC(i7-8700 / GTX 1060 / RAM 32GB)에서 도민이 직접 실행하는 것을 전제로 한다.
카드 데이터는 반출이 제한될 수 있으므로 **주 실행 형태는 센터 로컬 실행**이고, 공개 웹은 합성 샘플 시연용이다.

| | 센터 로컬 (주) | 공개 웹 시연 (보조) |
|---|---|---|
| 데이터 | 실데이터 (`DATA_MODE=real`) | 합성 샘플만 |
| DB | SQLite 파일 | Neon PostgreSQL |
| 계정 | 없음 (`AUTH_REQUIRED=false`) | 필요 (`AUTH_REQUIRED=true`) |
| HTTPS | 자체 서명 인증서 (localhost) | 플랫폼 인증서 + HSTS |
| 외부 의존 | 없음 | Vercel, Neon |

## 1. Render 대신 쓸 무료 서버 (2026-11 조사 기준)

| 선택지 | 무료 범위 | 카드 등록 | 맞는 경우 | 주의 |
|---|---|---|---|---|
| **Vercel Python Function (권장)** | Hobby 무료, Python 번들 500MB | 불필요 | 이미 쓰는 Vercel 에 API 까지 올림 → 서비스 하나 줄어듦 | 상업적 이용은 Hobby 약관상 불가, 서버리스라 파일 저장 불가(Neon 필요) |
| Google Cloud Run | 월 200만 요청, 18만 vCPU-초 | 필요(결제 계정) | 컨테이너 그대로, 무료 한도가 넉넉 | 한도 초과 시 과금 → 예산 알림 설정 필수 |
| Koyeb | 웹 서비스 1개(512MB) | 필요($29 보류 승인) | 상시 구동 1개 | 계정당 1개뿐, 2026-02 무카드 플랜 폐지 |
| Hugging Face Spaces | CPU 2 vCPU/16GB | 불필요 | — | Docker Space 무료 여부가 자료마다 다름 → 가입 후 확인 필요 |
| Fly.io | 신규 계정 무료 없음 | 필요 | 해당 없음 | — |

권장 이유: 이 프로젝트는 무거운 통계 패키지를 빼고 NumPy·pandas 만 쓰도록 만들어 Vercel 번들 한도 안에 들어가게 했다.
프런트와 API 가 **같은 출처**가 되므로 쿠키를 `SameSite=Lax` 로 두고 CORS 예외를 열 필요가 없어 보안 설정도 가장 단순하다.
개인정보 측면: Vercel·Neon·Google Cloud 는 모두 DPA(데이터 처리 계약)를 제공하는 사업자다. 다만 서버가 해외 리전이므로
이메일을 저장한다면 개인정보처리방침에 **국외 이전** 사실을 적어야 한다(센터 모드는 해당 없음).

> 위 무료 범위는 2026년 조사 자료 기준이고 자주 바뀐다. 가입 직전에 각 사 요금 페이지를 다시 확인할 것.

## 2. Vercel + Neon 배포 절차 (실제 배포로는 미검증)

1. Neon 에서 프로젝트 생성 → 연결 문자열 복사 (`sslmode=require` 포함).
2. Vercel 에서 저장소를 가져온다. Root Directory 는 저장소 루트 그대로(`vercel.json` 이 빌드·라우팅을 지정).
3. Vercel 환경변수(Production)에 등록 — 값은 `python backend/scripts/gen_keys.py` 로 생성:
   `APP_ENV=production`, `CORS_ORIGIN=https://<내 도메인>`, `TRUSTED_HOSTS=<내 도메인>`,
   `JWT_SECRET`, `DATA_KEYS`, `ACTIVE_KEY_ID`, `INDEX_KEY`, `DATABASE_URL`, `AUTH_REQUIRED=true`, `DATA_MODE=sample`
4. 배포 후 `https://<내 도메인>/api/health` 가 `{"status":"ok"}` 인지 확인.

프런트와 API 를 다른 도메인에 두는 경우에만: 프런트 `VITE_API_BASE=https://<API 도메인>`, 백엔드 `COOKIE_SAMESITE=none`,
`CORS_ORIGIN=https://<프런트 도메인>`.

## 3. 키 관리

| 키 | 용도 | 보관 | 교체 |
|---|---|---|---|
| `DATA_KEYS` (AES-256) | 이메일·질문 원문 필드 암호화 | 배포 플랫폼의 암호화된 환경변수. DB·저장소와 분리 | `scripts/rotate_keys.py` (무중단, 연 1회 또는 유출 의심 시) |
| `INDEX_KEY` (HMAC) | 이메일 블라인드 인덱스 | 위와 같음, 데이터 키와 **다른 값** | 교체 시 전 사용자 색인 재계산 필요 |
| `JWT_SECRET` | 세션 토큰 서명 | 위와 같음 | 교체하면 전원 재로그인 |
| DB 비밀번호 | Neon 접속 | `DATABASE_URL` | Neon 콘솔에서 재발급 |

- 키와 암호문을 다른 곳에 둔다(키=Vercel, 암호문=Neon). DB 만 유출돼서는 복호화할 수 없다.
- 운영/미리보기 환경에 서로 다른 키를 쓴다. 키를 로그·오류 메시지·제출 ZIP 에 넣지 않는다.
- 규모가 커지면 `DATA_KEYS` 를 KMS(예: Google Cloud KMS, AWS KMS)의 키로 감싸는 봉투 암호화로 옮긴다.
  `FieldCipher` 의 키 로딩 부분만 바꾸면 된다.

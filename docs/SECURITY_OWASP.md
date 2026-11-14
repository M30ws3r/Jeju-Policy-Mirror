# 보안 설계와 OWASP Top 10 점검

기준: OWASP Top 10:2021 (괄호는 2025판 대응 항목). 작성한 코드를 스스로 검토해 찾은 취약점과 조치를 함께 적었다.

## 1. 요구사항 반영 요약

| 요구 | 구현 | 위치 | 테스트 |
|---|---|---|---|
| HTTPS | 운영에서 평문 요청 거부, HSTS, Secure 쿠키, 로컬도 TLS 인증서 | `main.py` security_layer, `scripts/gen_dev_cert.py` | `test_session_cookie_flags_and_security_headers` |
| 입력 검증·정제 (라이브러리) | pydantic(형식·길이·허용 목록, 미정의 필드 거부) + nh3(HTML 제거), 프런트 zod | `schemas.py`, `security.sanitize_text`, `validation.ts` | `test_validation_…`, `test_html_is_stripped…` |
| 비밀번호 bcrypt | bcrypt cost 12, 72바이트 초과 거부 | `security.hash_password` | `test_password_is_bcrypt…` |
| SQL Injection 방지 | SQLAlchemy 바인드 파라미터만 사용, 문자열 조립 질의 없음 | `db.py`, `main.py` | `test_sql_injection_payload_is_inert` |
| 오류 메시지 | 일반 문구 + 요청 ID 만 응답, 상세는 서버 로그 | `main.py` 예외 처리기 | `test_validation_and_errors_hide_internals` |
| CORS | 출처 1개(기본 `https://myapp.com`), `*`·http·복수 출처는 기동 거부, credentials 허용 | `config.py`, `main.py` | `test_cors_…` 2건 |
| 개인정보 암호화 | AES-256-GCM 필드 암호화 + AAD 행 결합 + 키 버전, HMAC 블라인드 인덱스 | `security.FieldCipher` | `test_field_cipher_…`, `test_question_is_not_stored_in_plaintext` |
| 키 관리 | 환경변수 키링, 무중단 교체 스크립트, 운영에서 키 없으면 기동 거부 | `config.py`, `scripts/rotate_keys.py`, `docs/DEPLOY.md` | `test_production_requires_secrets` |

CORS 핵심 코드:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],   # 기본 "https://myapp.com", '*' 는 설정 단계에서 거부
    allow_credentials=True,                 # 인증 쿠키 허용
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
```

## 2. OWASP Top 10 항목별 점검

| 항목 | 상태 | 적용한 통제 | 남은 위험 |
|---|---|---|---|
| A01 접근 통제 실패 (2025 A01) | 대응 | 분석 결과·PDF 는 소유자만, 남의 것은 404(존재 여부 비공개). ID 는 UUID4. CSRF 토큰(쿠키=헤더) | 비로그인(키오스크) 결과는 ID 를 아는 사람이 열 수 있음 → 아래 V5 |
| A02 암호화 실패 (2025 A04) | 대응 | TLS 강제, AES-256-GCM, bcrypt, 키·암호문 분리 보관, DB 접속 `sslmode=require` | 키가 환경변수에 평문으로 존재 → 규모 확대 시 KMS |
| A03 인젝션 (2025 A05) | 대응 | ORM 바인딩, HTML 정제, PDF 출력 이스케이프, React 자동 이스케이프, CSP `script-src 'self'` | LLM 프롬프트 주입 → 아래 V6 |
| A04 불안전한 설계 (2025 A06) | 대응 | 개인정보 최소 수집(이메일만), 센터 모드 무계정, 로그인·분석 요청 제한, 본문 16KB 제한 | 요청 제한이 메모리 기반 → V2, V3 |
| A05 보안 설정 오류 (2025 A02) | 대응 | 보안 헤더, 운영에서 API 문서 비공개, Host 헤더 허용 목록, 위험 설정은 기동 거부 | — |
| A06 취약·노후 구성요소 (2025 A03 공급망) | 일부 | 의존성 최소화(통계 패키지 미사용), `package-lock.json` | 파이썬 버전 미고정 → V7 |
| A07 인증 실패 (2025 A07) | 대응 | 계정 열거 방지(동일 응답·동일 연산 시간), 시도 제한, HttpOnly·Secure·SameSite 쿠키, JWT 알고리즘 고정 | 서버 측 세션 폐기 없음 → V4. 다중 인증 없음 |
| A08 무결성 실패 (2025 A08) | 대응 | 역직렬화는 JSON 만, 외부 스크립트·CDN 없음, 파일 업로드 기능 없음 | — |
| A09 로깅·모니터링 실패 (2025 A09) | 일부 | 감사 로그(가입·로그인 성공/실패·분석), 요청 ID. 로그에 개인정보·질문 원문 없음 | 경보(알림) 체계 없음 → 운영 시 플랫폼 로그 알림 설정 |
| A10 SSRF (2025 A10 예외 처리) | 대응 | 사용자 입력으로 URL 을 만들지 않음. LLM 주소는 환경변수 + https/localhost 만. 미처리 예외는 일반 500 | — |

## 3. 자체 검토에서 찾은 취약점과 수정

### V1. 질문 원문이 결과 JSON 에 평문으로 남음 — **수정 완료**
`question_enc` 는 암호화했지만 `result_json` 안에 같은 질문이 평문으로 들어가 암호화가 무의미했다.
```python
# 수정 전
record = Analysis(..., result_json=json.dumps(result, ensure_ascii=False))
# 수정 후: 질문은 암호화 컬럼에만 둔다
stored = {k: v for k, v in result.items() if k != "question"}
record = Analysis(..., result_json=json.dumps(stored, ensure_ascii=False))
```
검증: `test_question_is_not_stored_in_plaintext`.

### V2. 요청 제한 키가 위조 가능한 `X-Forwarded-For` 를 신뢰 — **미수정, 수정안 제시**
공격자가 헤더를 바꿔 가며 IP 기준 제한을 피할 수 있다(계정 기준 제한은 유효). 플랫폼이 덧붙이는 마지막 값만 믿도록 바꾼다.
```python
def client_key(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    hops = [h.strip() for h in fwd.split(",") if h.strip()]
    # 신뢰 프록시가 1단이면 맨 오른쪽 값이 프록시가 본 실제 주소
    return hops[-1] if hops else (request.client.host if request.client else "unknown")
```
프록시 단수는 플랫폼마다 다르므로 배포 환경에서 확인 후 적용해야 해서 기본 코드에는 넣지 않았다.

### V3. 서버리스에서 메모리 기반 제한이 인스턴스마다 따로 동작 — **미수정, 수정안 제시**
Vercel 처럼 인스턴스가 여러 개면 시도 횟수가 합산되지 않는다. 감사 로그 테이블로 센다.
```python
window = datetime.now(timezone.utc) - timedelta(minutes=5)
fails = session.scalar(select(func.count()).select_from(AuditEvent).where(
    AuditEvent.kind == "login_fail", AuditEvent.user_id == user.id, AuditEvent.created_at >= window))
if fails >= 8:
    raise fail(429, "too_many", "로그인 시도가 너무 많습니다. 5분 후 다시 시도해 주세요.")
```
센터 로컬(단일 프로세스)에서는 현재 구현으로 충분하다.

### V4. 로그아웃해도 탈취된 토큰은 만료(60분)까지 유효 — **미수정, 수정안 제시**
`users.token_version` 컬럼을 두고 토큰에 `ver` 를 담아 비교, 로그아웃·비밀번호 변경 시 +1 한다.
```python
payload = {"sub": user.id, "ver": user.token_version, ...}
# 검증 시
if payload["ver"] != user.token_version: return None
```

### V5. 비로그인 분석 결과는 ID 만 알면 열람 가능 — **설계상 수용**
키오스크 모드에는 사용자 식별 수단이 없다. ID 가 122비트 난수라 추측은 불가능하고, 결과에는 집계 통계만 있다.
공개 웹은 `AUTH_REQUIRED=true` 로 운영하면 해당 없음.

### V6. LLM 프롬프트 주입 — **완화**
질문은 구분자 안의 데이터로만 전달하고, LLM 출력은 (a) 지역·업종 허용 목록과 연월 정규식으로 재검증,
(b) 설명문은 수치 잠금·인과 표현 금지 규칙을 통과해야만 사용한다. LLM 은 DB·파일·등급 판정에 접근하지 못한다.
최악의 경우에도 '엉뚱한 지역이 선택됨' 수준이고 사용자가 화면에서 확인·수정한다.

### V7. 파이썬 의존성 버전 미고정 — **미수정, 수정안 제시**
`requirements.txt` 가 하한(`>=`)만 지정한다. 제출 전 해시까지 고정한다.
```bash
pip install pip-tools
pip-compile --generate-hashes -o requirements.lock backend/requirements.txt
pip install --require-hashes -r requirements.lock
```

### V8. 비밀번호 유출 목록 대조 없음 — **미수정**
길이·구성 규칙만 검사한다. 공개 서비스로 키울 때 유출 비밀번호 대조(k-익명 방식 API)를 추가한다.

## 4. 개인정보 처리 원칙

- 수집: 이메일, 비밀번호(해시). 그 밖의 개인정보는 받지 않는다. 센터 모드는 수집 없음.
- 저장: 이메일·질문 원문은 암호문, 조회는 블라인드 인덱스. 화면에는 마스킹(`ab***@도메인`)만 표시.
- 분석 데이터: 지역·업종 단위 집계뿐이며 개인 단위 정보가 없다.
- 제출물: API 키·`.env`·실데이터·인증서는 `.gitignore` 로 제외.

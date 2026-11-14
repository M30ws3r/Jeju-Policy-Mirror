# 공개 URL 만들기 (Vercel, 무료)

화면과 API 를 Vercel 프로젝트 하나에 함께 올린다. Render 는 쓰지 않는다.
**이 절차는 실제 배포로 시험하지 않았다.** 막히는 단계가 있으면 오류 화면을 그대로 공유할 것.

## 0. 올리기 전에 확인

- `backend/data/real/` 에 `bus_monthly.csv`, `card_emd_monthly_202212_202507.csv` 두 집계본이 있어야 실데이터 화면이 나온다.
  (`.gitignore` 가 이 두 파일만 저장소에 넣도록 설정돼 있다. 원본 일자 파일 `bus_days/` 는 올라가지 않는다.)
- `.env`, 인증서, API 키는 저장소에 올라가지 않는다(`.gitignore`).

## 1. GitHub 저장소 (GitHub Desktop)

1. File → Add local repository → `Jeju Policy Mirror` 폴더 선택 → "create a repository" 안내가 나오면 생성.
2. **커밋 작성자 이메일 확인**: File → Options → Git 에서 이메일을 `…@users.noreply.github.com` 로 선택.
3. 첫 커밋 → Publish repository (Private 가능).

## 2. 비밀값 만들기

```bat
cd backend
python scripts\gen_keys.py
```
출력된 4줄(`JWT_SECRET`, `DATA_KEYS`, `ACTIVE_KEY_ID`, `INDEX_KEY`)을 메모장에 잠시 둔다. 어디에도 커밋하지 않는다.

## 3. Vercel

1. vercel.com 에 GitHub 계정으로 가입 → Add New → Project → 위 저장소 Import.
2. Framework Preset: **Other**, Root Directory: 저장소 최상위(그대로). 빌드 설정은 `vercel.json` 이 지정한다.
3. Environment Variables 에 아래를 넣는다. `<도메인>` 은 Vercel 이 정해 주는 주소(예: `jeju-policy-mirror.vercel.app`)다.
   처음 배포 전에는 주소를 모르므로, 프로젝트 이름으로 예상 주소를 넣고 배포 후 다르면 고쳐서 Redeploy 한다.

| 이름 | 값 |
|---|---|
| `APP_ENV` | `production` |
| `CORS_ORIGIN` | `https://<도메인>` |
| `TRUSTED_HOSTS` | `<도메인>` |
| `JWT_SECRET` `DATA_KEYS` `ACTIVE_KEY_ID` `INDEX_KEY` | 2단계 출력값 |
| `DATABASE_URL` | `sqlite:////tmp/jpm.db` (시연용, 재시작 시 초기화) 또는 Neon 연결 문자열 |
| `AUTH_REQUIRED` | `false` (시연용: 계정 없이 사용, 개인정보 저장 없음) |
| `DATA_MODE` | `sample` (아래쪽 자유 질문 시연용. 실데이터 사례는 별도로 항상 표시) |

4. Deploy → 완료 후 `https://<도메인>/api/health` 가 `{"status":"ok"}` 인지, 첫 화면 위쪽 사례 버튼이 동작하는지 확인.

## 4. 주의

- Vercel 서버는 파일을 쓸 수 없어 `DATABASE_URL` 을 반드시 지정해야 한다(`/tmp` 또는 Neon).
- Hobby(무료) 플랜은 비상업 용도다. 사업화 단계에서는 유료 플랜이나 다른 서버로 옮긴다.
- 서버가 해외 리전이다. 계정 기능을 켜서 이메일을 저장하면 개인정보처리방침에 국외 이전을 적어야 한다(`AUTH_REQUIRED=false` 면 해당 없음).

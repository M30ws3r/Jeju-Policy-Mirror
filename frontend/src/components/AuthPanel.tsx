import { type FormEvent, useState } from "react";
import { api, ApiFailure } from "../api";
import { credentialsSchema, firstError } from "../validation";

interface Props {
  user: string | null;
  required: boolean;
  onChange: (user: string | null) => void;
}

export function AuthPanel({ user, required, onChange }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) {
    return (
      <div className="auth signed">
        <span>{user} 로 로그인됨</span>
        <button
          type="button"
          className="link"
          onClick={async () => {
            await api.logout().catch(() => undefined);
            onChange(null);
          }}
        >
          로그아웃
        </button>
      </div>
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = credentialsSchema.safeParse({ email, password });
    const message = firstError(parsed);
    if (!parsed.success || message) {
      setError(message ?? "입력값을 확인해 주세요.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.auth(mode, parsed.data.email, parsed.data.password);
      setPassword("");
      onChange(await api.me());
    } catch (err) {
      setError(err instanceof ApiFailure ? err.message : "요청을 처리할 수 없습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="auth" open={required}>
      <summary>{required ? "로그인이 필요합니다" : "로그인하면 분석 기록이 저장됩니다 (선택)"}</summary>
      <form onSubmit={submit} noValidate>
        <label>
          이메일
          <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} required />
        </label>
        <label>
          비밀번호 (10자 이상, 영문+숫자)
          <input
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            maxLength={72}
            required
          />
        </label>
        <div className="actions">
          <button type="submit" disabled={busy}>
            {mode === "login" ? "로그인" : "가입하기"}
          </button>
          <button type="button" className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "처음이면 가입" : "이미 계정이 있음"}
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <p className="small">저장 항목은 이메일(암호화)과 비밀번호 해시뿐이며, 분석에는 개인 단위 데이터가 쓰이지 않습니다.</p>
      </form>
    </details>
  );
}

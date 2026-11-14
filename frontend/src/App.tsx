import { type FormEvent, useEffect, useState } from "react";
import { api, ApiFailure } from "./api";
import { AuthPanel } from "./components/AuthPanel";
import { ResultView } from "./components/ResultView";
import type { AnalysisResult, Meta } from "./types";
import { firstError, monthSchema, questionSchema } from "./validation";

const EXAMPLES = [
  "2024년 7월 함덕 버스 노선을 조정한 뒤 지역 소비가 늘었나요?",
  "2024년 7월 성산 버스 노선 조정으로 소비가 늘었나요?",
  "2024년 7월 함덕 버스 노선 조정 후 식당 매출이 늘었나요?",
];

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [user, setUser] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [area, setArea] = useState("");
  const [month, setMonth] = useState("");
  const [industry, setIndustry] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .meta()
      .then((m) => {
        setMeta(m);
        if (m.signed_in) void api.me().then(setUser);   // 로그인 상태일 때만 세션 확인
      })
      .catch(() => setError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."));
  }, []);

  async function run(text: string, overrides = { area, month, industry }) {
    const message = firstError(questionSchema.safeParse(text));
    if (message) return setError(message);
    if (overrides.month && firstError(monthSchema.safeParse(overrides.month))) return setError("연월을 다시 선택해 주세요.");
    setBusy(true);
    setError("");
    try {
      const data = await api.analyze({
        question: text.trim(),
        ...(overrides.area ? { area: overrides.area } : {}),
        ...(overrides.month ? { policy_month: overrides.month } : {}),
        ...(overrides.industry ? { industry: overrides.industry } : {}),
      });
      setResult(data);
      // 에이전트가 해석한 조건을 화면에 채워, 사용자가 확인하고 고칠 수 있게 한다.
      setArea(data.spec.area ?? "");
      setMonth(data.spec.policy_month ?? "");
      setIndustry(data.spec.industry ?? "");
    } catch (err) {
      setResult(null);
      setError(err instanceof ApiFailure ? err.message : "요청을 처리할 수 없습니다.");
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(question);
  }

  const locked = !!meta?.auth_required && !user;

  return (
    <div className="page">
      <header>
        <h1>Jeju Policy Mirror</h1>
        <p>정책을 시행한 뒤 정말 달라졌는지, 계절이나 관광객 변화 때문은 아닌지 데이터로 확인합니다.</p>
        {meta && <p className="small">사용 자료: {meta.data_label}</p>}
      </header>

      {meta && <AuthPanel user={user} required={meta.auth_required} onChange={setUser} />}

      <form className="card ask" onSubmit={submit} noValidate>
        <label htmlFor="q">궁금한 점을 문장으로 적어 주세요</label>
        <textarea
          id="q"
          rows={2}
          maxLength={500}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="예) 2024년 7월 함덕 버스 노선을 조정한 뒤 지역 소비가 늘었나요?"
          disabled={locked}
        />
        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              className="chip"
              disabled={locked || busy}
              onClick={() => {
                setQuestion(ex);
                void run(ex, { area: "", month: "", industry: "" });
              }}
            >
              {ex}
            </button>
          ))}
        </div>

        {meta && (
          <fieldset>
            <legend>분석 조건 (질문에서 자동으로 채워지며, 직접 고칠 수 있습니다)</legend>
            <label>
              지역
              <select value={area} onChange={(e) => setArea(e.target.value)} disabled={locked}>
                <option value="">질문에서 찾기</option>
                {meta.areas.map((a) => (
                  <option key={a}>{a}</option>
                ))}
              </select>
            </label>
            <label>
              정책 시행 연월
              <input type="month" value={month} min={meta.first_month} max={meta.last_month} onChange={(e) => setMonth(e.target.value)} disabled={locked} />
            </label>
            <label>
              업종
              <select value={industry} onChange={(e) => setIndustry(e.target.value)} disabled={locked}>
                <option value="">질문에서 찾기</option>
                {meta.industries.map((i) => (
                  <option key={i}>{i}</option>
                ))}
              </select>
            </label>
          </fieldset>
        )}

        <div className="actions">
          <button type="submit" disabled={busy || locked}>
            {busy ? "분석하는 중…" : "분석하기"}
          </button>
          {error && (
            <span className="error" role="alert">
              {error}
            </span>
          )}
        </div>
      </form>

      {result?.status === "needs_input" && <p className="notice">{result.message}</p>}
      {result?.status === "done" && <ResultView result={result} />}

      <footer className="small">
        이 도구는 관측 자료를 분석합니다. 비교 조건이 맞지 않으면 인과효과 대신 관측된 사실만 보고합니다.
      </footer>
    </div>
  );
}

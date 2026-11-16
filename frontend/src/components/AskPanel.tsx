// 실데이터 자유 질문: 노선 번호 + 시행 연월이 들어간 문장을 받아 에이전트가 같은 점검을 수행한다.
import { useState } from "react";
import { z } from "zod";
import { askApi, type AskResponse } from "../askApi";
import { CaseFailure } from "../casesApi";
import { CaseResultView } from "./CaseResultView";

const questionSchema = z.string().trim().min(2, "질문을 입력해 주세요.").max(300, "300자 이내로 입력해 주세요.");
const EXAMPLES = [
  "2024년 8월 감차 이후 311번 이용객은 얼마나 변했나요?",
  "2024년 8월 326번을 폐지하고 325번으로 합친 뒤 이용객은 유지됐나요?",
  "2024년 8월 개편 후 201번 이용객이 줄었나요?",
];

export function AskPanel() {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(text: string) {
    const parsed = questionSchema.safeParse(text);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "질문을 확인해 주세요.");
      return;
    }
    setQuestion(parsed.data);
    setBusy(true);
    setError("");
    try {
      setResult(await askApi.ask(parsed.data));
      setAsked(parsed.data);
    } catch (err) {
      setResult(null);
      setError(err instanceof CaseFailure ? err.message : "요청을 처리할 수 없습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card cases">
      <h2>직접 질문하기 — 실데이터</h2>
      <p className="small">
        노선 번호와 정책 시행 연월을 넣어 문장으로 물어보세요. 여러 노선을 적으면 합산해 하나로 봅니다. 위 사례와 같은 실데이터·같은 점검을 거칩니다.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(question);
        }}
      >
        <textarea
          value={question}
          maxLength={300}
          rows={2}
          placeholder="예) 2024년 8월 감차 이후 311번 이용객은 얼마나 변했나요?"
          onChange={(e) => setQuestion(e.target.value)}
        />
        <div className="examples">
          {EXAMPLES.map((q) => (
            <button key={q} type="button" className="chip" disabled={busy} onClick={() => void run(q)}>
              {q}
            </button>
          ))}
        </div>
        <button type="submit" disabled={busy}>
          {busy ? "분석하는 중…" : "분석하기"}
        </button>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result?.status === "needs_input" && !busy && (
        <p className="notice">
          {result.message} (분석 가능한 시행 연월: {result.options.first_month} ~ {result.options.last_month})
        </p>
      )}
      {result?.status === "done" && !busy && <CaseResultView result={result} onPdf={() => askApi.downloadPdf(asked)} />}
    </section>
  );
}

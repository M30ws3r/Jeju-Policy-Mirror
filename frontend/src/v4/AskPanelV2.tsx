// 실데이터 자유 질문 v2: 입력창과 '분석하기' 버튼을 한 묶음으로, 예시 질문은 그 아래 따로 둔다.
// 새 파일로 만든 이유: 기존 AskPanel 은 예시 버튼 바로 밑에 분석 버튼이 붙어 있어 무엇을 누르는지 헷갈렸다.
import { useState } from "react";
import { z } from "zod";
import { askApi, type AskResponse } from "../askApi";
import { CaseFailure } from "../casesApi";
import { CaseResultView } from "../components/CaseResultView";

const questionSchema = z.string().trim().min(2, "질문을 입력해 주세요.").max(300, "300자 이내로 입력해 주세요.");
const EXAMPLES = [
  "2024년 8월 감차 이후 311번 이용객은 얼마나 변했나요?",
  "2024년 8월 326번을 폐지하고 325번으로 합친 뒤 이용객은 유지됐나요?",
  "2024년 8월 개편 후 201번 이용객이 줄었나요?",
];

export function AskPanelV2() {
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
      setError(err instanceof CaseFailure ? err.message : "분석하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ask-v2">
      <form
        className="ask-box"
        onSubmit={(e) => {
          e.preventDefault();
          void run(question);
        }}
      >
        <label htmlFor="ask-q" className="sr-only">
          질문
        </label>
        <textarea
          id="ask-q"
          value={question}
          maxLength={300}
          rows={2}
          placeholder="예) 2024년 8월 감차 이후 311번 이용객은 얼마나 변했나요?"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void run(question);
            }
          }}
        />
        <button type="submit" disabled={busy}>
          {busy ? "분석하는 중…" : "분석하기"}
        </button>
      </form>
      <div className="ask-examples">
        <p>이렇게 물어볼 수 있습니다</p>
        <ul>
          {EXAMPLES.map((q) => (
            <li key={q}>
              <button type="button" disabled={busy} onClick={() => void run(q)}>
                {q}
              </button>
            </li>
          ))}
        </ul>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result?.status === "needs_input" && !busy && (
        <p className="needs">
          {result.message} 분석할 수 있는 시행 연월은 {result.options.first_month}부터 {result.options.last_month}까지입니다.
        </p>
      )}
      {result?.status === "done" && !busy && <CaseResultView result={result} onPdf={() => askApi.downloadPdf(asked)} />}
    </div>
  );
}

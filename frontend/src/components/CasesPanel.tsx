// 버스 실데이터 정책 사례 목록 + 결과.
import { useEffect, useState } from "react";
import { CaseFailure, casesApi, type CaseItem, type CaseResult } from "../casesApi";
import { CaseResultView } from "./CaseResultView";

export function CasesPanel() {
  const [items, setItems] = useState<CaseItem[]>([]);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [selected, setSelected] = useState("");
  const [result, setResult] = useState<CaseResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    casesApi
      .list()
      .then((r) => {
        setItems(r.items);
        setAvailable(r.available);
      })
      .catch(() => setAvailable(false));
  }, []);

  async function open(id: string) {
    setSelected(id);
    setBusy(true);
    setError("");
    try {
      setResult(await casesApi.get(id));
    } catch (err) {
      setResult(null);
      setError(err instanceof CaseFailure ? err.message : "요청을 처리할 수 없습니다.");
    } finally {
      setBusy(false);
    }
  }

  if (available === null) return null;

  return (
    <section className="card cases">
      <h2>실제 제주 정책 검증 — 2024년 8월 버스 노선 개편</h2>
      <p className="small">
        제주데이터허브 일일 노선별 버스 이용자 정보(API)로 분석합니다. 사례를 누르면 에이전트가 비교 노선을 고르고 점검한 결과를 보여 줍니다.
      </p>
      {!available ? (
        <p className="notice">버스 실데이터가 아직 준비되지 않았습니다. 실행 매뉴얼의 수집 절차를 마친 뒤 다시 열어 주세요.</p>
      ) : (
        <div className="examples">
          {items.map((c) => (
            <button key={c.id} type="button" className={`chip${selected === c.id ? " chip-on" : ""}`} disabled={busy} onClick={() => void open(c.id)}>
              {c.question}
            </button>
          ))}
        </div>
      )}
      {busy && <p className="small">분석하는 중…</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result && !busy && <CaseResultView result={result} />}
    </section>
  );
}

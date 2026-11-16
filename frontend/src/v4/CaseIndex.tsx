// 실제 정책 사례를 '목차'처럼 보여 준다. 줄을 누르면 그 아래에 분석 결과가 열린다.
import { useEffect, useState } from "react";
import { CaseFailure, casesApi, type CaseItem, type CaseResult } from "../casesApi";
import { CaseResultView } from "../components/CaseResultView";

const routesOf = (label: string) => label.match(/\d{3}/g) ?? [];

export function CaseIndex() {
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
    if (id === selected && result) {
      setSelected("");
      setResult(null);
      return;
    }
    setSelected(id);
    setBusy(true);
    setError("");
    try {
      setResult(await casesApi.get(id));
    } catch (err) {
      setResult(null);
      setError(err instanceof CaseFailure ? err.message : "결과를 불러오지 못했습니다. 잠시 후 다시 눌러 주세요.");
    } finally {
      setBusy(false);
    }
  }

  if (available === null) return null;
  if (!available) return <p className="quiet">버스 실데이터가 아직 준비되지 않았습니다. 실행 매뉴얼의 수집 절차를 마친 뒤 다시 열어 주세요.</p>;

  return (
    <div className="case-index">
      <ul>
        {items.map((c) => {
          const on = selected === c.id;
          return (
            <li key={c.id} className={on ? "on" : undefined}>
              <button type="button" aria-expanded={on} disabled={busy && !on} onClick={() => void open(c.id)}>
                <span className="routes">
                  {routesOf(c.label).map((n) => (
                    <span key={n}>{n}</span>
                  ))}
                </span>
                <span className="q">{c.question}</span>
                <span className="kind">{c.policy.replace("2024년 8월 ", "")}</span>
              </button>
              {on && (
                <div className="case-body">
                  {busy && <p className="quiet">비교 노선을 고르고 점검하는 중입니다…</p>}
                  {error && (
                    <p className="error" role="alert">
                      {error}
                    </p>
                  )}
                  {result && !busy && <CaseResultView result={result} />}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

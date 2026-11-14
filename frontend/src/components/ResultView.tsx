import { useState } from "react";
import { api, ApiFailure } from "../api";
import type { AnalysisResult, CheckStatus, Level } from "../types";
import { Chart } from "./Chart";

const LEVEL_TEXT: Record<Level, string> = {
  A: "A · 준실험 근거 충족",
  B: "B · 잠정 추정",
  C: "C · 연관성만 보고",
};
const STATUS_TEXT: Record<CheckStatus, string> = { pass: "통과", warn: "주의", fail: "미충족" };
const signed = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;

export function ResultView({ result }: { result: AnalysisResult }) {
  const [pdfError, setPdfError] = useState("");
  const [busy, setBusy] = useState(false);
  const { verdict, estimates, checks, series, spec, observed } = result;
  if (!verdict) return null;
  const did = estimates?.did;

  async function download() {
    if (!result.analysis_id) return;
    setBusy(true);
    setPdfError("");
    try {
      await api.downloadPdf(result.analysis_id);
    } catch (err) {
      setPdfError(err instanceof ApiFailure ? err.message : "PDF 를 만들 수 없습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="result" aria-live="polite">
      {result.data_source.mode === "sample" && (
        <p className="notice">합성 샘플 데이터로 만든 시연 결과입니다. 실제 제주 정책의 효과가 아닙니다.</p>
      )}

      <article className={`card verdict level-${verdict.level}`}>
        <span className="badge">{LEVEL_TEXT[verdict.level]}</span>
        {did ? (
          <p className="headline">
            <strong>{signed(did.effect_pct)}</strong>
            <span>
              95% 신뢰구간 {signed(did.ci_low)} ~ {signed(did.ci_high)}
            </span>
          </p>
        ) : (
          <p className="headline muted">
            <strong>인과효과 추정 안 함</strong>
            {observed?.area_yoy_pct !== undefined && <span>관측: 전년 같은 달 대비 {signed(observed.area_yoy_pct)}</span>}
          </p>
        )}
        <p>{verdict.statement}</p>
        {verdict.plain_explanation && <p className="plain">쉬운 설명: {verdict.plain_explanation}</p>}
        <div className="actions">
          <button type="button" onClick={download} disabled={busy || !result.analysis_id}>
            {busy ? "PDF 만드는 중…" : "정책 검토 PDF 내려받기"}
          </button>
          {pdfError && <span className="error">{pdfError}</span>}
        </div>
      </article>

      {series?.months && series.treated && series.control && spec.area && spec.policy_month && (
        <article className="card">
          <h2>시행 전후 흐름</h2>
          <Chart months={series.months} treated={series.treated} control={series.control} policyMonth={spec.policy_month} areaName={spec.area} />
          {result.controls && (
            <p className="small">
              비교 지역: {result.controls.map((c) => `${c.area}(유사도 ${c.score})`).join(", ")}
              {result.excluded_neighbors?.length ? ` · 인접 지역 제외: ${result.excluded_neighbors.join(", ")}` : ""}
            </p>
          )}
        </article>
      )}

      {checks && (
        <article className="card">
          <h2>정책 효과라고 말해도 되는지 점검한 항목</h2>
          <table>
            <thead>
              <tr>
                <th scope="col">항목</th>
                <th scope="col">결과</th>
                <th scope="col">내용</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((c) => (
                <tr key={c.id}>
                  <th scope="row">
                    {c.label}
                    {c.required && <span className="req"> 필수</span>}
                  </th>
                  <td>
                    <span className={`status status-${c.status}`}>{STATUS_TEXT[c.status]}</span>
                  </td>
                  <td>{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
      )}

      <article className="card">
        <h2>에이전트가 수행한 단계</h2>
        <ol className="steps">
          {result.steps.map((s) => (
            <li key={s.name}>
              <strong>{s.name}</strong> — {s.summary}
            </li>
          ))}
        </ol>
        <h2>한계와 유의사항</h2>
        <ul className="small">
          {result.limitations?.map((l) => <li key={l}>{l}</li>)}
        </ul>
        <p className="small">데이터: {result.data_source.datasets.join(" / ")}</p>
      </article>
    </section>
  );
}

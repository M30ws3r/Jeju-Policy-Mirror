// 노선 단위 실데이터 결과 화면.
// 새 파일로 만든 이유: 기존 ResultView 는 '지역·비교 지역·업종' 문구와 저장된 분석 ID 기반 PDF 를 쓴다.
// 실데이터 사례는 '노선·비교 노선' 문구와 사례 ID 기반 PDF 가 필요해 따로 두었다. 그래프(Chart)는 그대로 재사용한다.
import { useState } from "react";
import { CaseFailure, casesApi, type CaseResult } from "../casesApi";
import type { CheckStatus, Level } from "../types";
import { Chart } from "./Chart";

const LEVEL_TEXT: Record<Level, string> = {
  A: "A · 준실험 근거 충족",
  B: "B · 잠정 추정",
  C: "C · 연관성만 보고",
};
const STATUS_TEXT: Record<CheckStatus, string> = { pass: "통과", warn: "주의", fail: "미충족" };
const signed = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
const people = (v?: number) => (v === undefined ? "-" : `${Math.round(v).toLocaleString("ko-KR")}명`);

// onPdf: 자유 질문 결과처럼 사례 ID 가 없는 경우 PDF 받는 방법을 바꿔 끼운다 (없으면 사례 PDF).
export function CaseResultView({ result, onPdf }: { result: CaseResult; onPdf?: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [pdfError, setPdfError] = useState("");
  const { verdict, estimates, checks, series, spec, observed } = result;
  if (!verdict) return null;
  const did = estimates?.did;

  async function download() {
    setBusy(true);
    setPdfError("");
    try {
      await (onPdf ? onPdf() : casesApi.downloadPdf(result.case_id));
    } catch (err) {
      setPdfError(err instanceof CaseFailure ? err.message : "PDF 를 만들 수 없습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="result" aria-live="polite">
      <article className={`card verdict level-${verdict.level}`}>
        <span className="badge">{LEVEL_TEXT[verdict.level]}</span>
        {did ? (
          <p className="headline">
            <strong>{signed(did.effect_pct)}</strong>
            <span>
              비교 노선 대비 · 95% 신뢰구간 {signed(did.ci_low)} ~ {signed(did.ci_high)}
            </span>
          </p>
        ) : (
          <p className="headline muted">
            <strong>인과효과 추정 안 함</strong>
          </p>
        )}
        <p>{verdict.statement}</p>
        <div className="actions">
          <button type="button" onClick={download} disabled={busy}>
            {busy ? "PDF 만드는 중…" : "정책 검토 PDF 내려받기"}
          </button>
          {pdfError && <span className="error">{pdfError}</span>}
        </div>
      </article>

      {observed && (
        <article className="card">
          <h2>관측된 사실 (하루 평균 승차 인원)</h2>
          <table>
            <thead>
              <tr>
                <th scope="col">항목</th>
                <th scope="col">시행 전</th>
                <th scope="col">시행 후</th>
                <th scope="col">변화</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">{spec.area}</th>
                <td>{people(observed.target_daily_pre)}</td>
                <td>{people(observed.target_daily_post)}</td>
                <td>{observed.before_after_pct != null ? signed(observed.before_after_pct) : "-"}</td>
              </tr>
              <tr>
                <th scope="row">전체 노선 합계 (참고)</th>
                <td>-</td>
                <td>-</td>
                <td>{observed.island_before_after_pct != null ? signed(observed.island_before_after_pct) : "-"}</td>
              </tr>
            </tbody>
          </table>
        </article>
      )}

      {series?.months && series.treated && series.control && spec.policy_month && (
        <article className="card">
          <h2>시행 전후 흐름</h2>
          <Chart months={series.months} treated={series.treated} control={series.control} policyMonth={spec.policy_month} areaName={spec.area ?? "대상 노선"} />
          {result.controls && <p className="small">비교 노선: {result.controls.map((c) => `${c.area}(유사도 ${c.score})`).join(", ")}</p>}
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
        <ul className="small">{result.limitations?.map((l) => <li key={l}>{l}</li>)}</ul>
        <p className="small">데이터: {result.data_source.datasets.join(" / ")}</p>
      </article>
    </section>
  );
}

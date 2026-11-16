// 첫 화면의 '거울': 같은 감차 노선을 단순 전후 비교로 보면 얼마, 비교 노선과 견주면 얼마인지 나란히 보여 준다.
// 수치는 고정값이 아니라 서버의 실데이터 결과(/api/cases/cut_2024)에서 읽는다.
import { useEffect, useState } from "react";
import { casesApi, type CaseResult } from "../casesApi";

const pct = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`;

export function HeroMirror() {
  const [r, setR] = useState<CaseResult | null>(null);
  useEffect(() => {
    casesApi.get("cut_2024").then(setR).catch(() => setR(null));
  }, []);
  const naive = r?.observed?.before_after_pct;
  const did = r?.estimates?.did;
  const island = r?.observed?.island_before_after_pct;
  if (naive == null || !did) return <div className="mirror mirror-empty" aria-hidden="true" />;

  return (
    <figure className="mirror">
      <div className="mirror-row naive">
        <p className="mirror-label">단순히 전후만 비교하면</p>
        <p className="mirror-value">
          <span className="strike">{pct(naive)}</span>
        </p>
      </div>
      <div className="mirror-row honest">
        <p className="mirror-label">비슷한 노선과 견주면</p>
        <p className="mirror-value">{pct(did.effect_pct)}</p>
        <p className="mirror-note">
          95% 신뢰구간 {pct(did.ci_low)} ~ {pct(did.ci_high)}. 0을 포함하므로 줄었다고 단정할 수 없습니다.
        </p>
      </div>
      <figcaption>
        2024년 8월 감차한 6개 노선(211, 212, 221, 222, 311, 800번)의 하루 평균 승차 인원
        {island != null && <>. 같은 기간 제주 전체 노선은 {pct(island)}</>}.
      </figcaption>
    </figure>
  );
}

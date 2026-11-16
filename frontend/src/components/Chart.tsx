interface Props {
  months: string[];
  treated: number[];
  control: number[];
  policyMonth: string;
  areaName: string;
}

const W = 720;
const H = 280;
const PAD = { left: 44, right: 16, top: 26, bottom: 34 };

/** 대상 지역(실선)과 비교 지역 평균(점선)의 지수 추이. 색에만 의존하지 않도록 선 모양과 직접 라벨을 함께 쓴다. */
// controlLabel·measure: 노선 단위 실데이터 화면에서 '비교 노선 평균', '승차 인원'으로 바꿔 쓰기 위한 선택 값 (기본값은 기존 문구)
export function Chart({ months, treated, control, policyMonth, areaName, controlLabel = "비교 지역 평균", measure = "카드 소비" }: Props & { controlLabel?: string; measure?: string }) {
  const all = [...treated, ...control];
  const lo = Math.floor(Math.min(...all) / 5) * 5;
  const hi = Math.ceil(Math.max(...all) / 5) * 5;
  const x = (i: number) => PAD.left + (i * (W - PAD.left - PAD.right)) / Math.max(months.length - 1, 1);
  const y = (v: number) => PAD.top + ((hi - v) * (H - PAD.top - PAD.bottom)) / Math.max(hi - lo, 1);
  const path = (values: number[]) => values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const policyIndex = months.indexOf(policyMonth);
  const ticks = [lo, lo + (hi - lo) / 2, hi];
  const yearMarks = months.map((m, i) => ({ m, i })).filter(({ m }) => m.endsWith("-01"));

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${areaName}과 ${controlLabel}의 ${measure} 지수 추이. 시행 시점 ${policyMonth}.`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} />
            <text className="axis" x={PAD.left - 8} y={y(t) + 4} textAnchor="end">
              {Math.round(t)}
            </text>
          </g>
        ))}
        {yearMarks.map(({ m, i }) => (
          <text key={m} className="axis" x={x(i)} y={H - 12} textAnchor="middle">
            {m.slice(0, 4)}
          </text>
        ))}
        {policyIndex >= 0 && (
          <g>
            <rect className="post-band" x={x(policyIndex)} y={PAD.top} width={W - PAD.right - x(policyIndex)} height={H - PAD.top - PAD.bottom} />
            <line className="policy-line" x1={x(policyIndex)} x2={x(policyIndex)} y1={PAD.top} y2={H - PAD.bottom} />
            <text className="policy-label" x={x(policyIndex)} y={PAD.top - 8} textAnchor="middle">
              시행 {policyMonth}
            </text>
          </g>
        )}
        <path className="line-control" d={path(control)} />
        <path className="line-treated" d={path(treated)} />
      </svg>
      <figcaption>
        <span className="legend legend-treated">{areaName} (실선)</span>
        <span className="legend legend-control">{controlLabel} (점선)</span>
        <span className="legend-note">시행 전 평균 = 100</span>
      </figcaption>
    </figure>
  );
}

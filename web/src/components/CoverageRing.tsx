// Coverage as a ring with the percentage in the middle. null draws an empty ring and a dash.
export function CoverageRing({ coverage, fits }: { coverage: number | null; fits: boolean }) {
  const r = 22
  const c = 2 * Math.PI * r
  const filled = coverage === null ? 0 : Math.max(0, Math.min(1, coverage)) * c
  return (
    <div className={fits ? 'ring ring-fits' : 'ring'}>
      <svg viewBox="0 0 52 52" width="56" height="56" aria-hidden="true" focusable="false">
        <circle className="ring-track" cx="26" cy="26" r={r} />
        <circle
          className="ring-fill"
          cx="26"
          cy="26"
          r={r}
          strokeDasharray={`${filled} ${c}`}
          transform="rotate(-90 26 26)"
        />
      </svg>
      <span className="ring-value num">{coverage === null ? '—' : `${(coverage * 100).toFixed(0)}%`}</span>
    </div>
  )
}

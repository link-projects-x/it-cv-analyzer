import { signed } from '../hints'

export type DeltaSign = 'positive' | 'negative' | 'zero'

// Sign of a value as printed with `digits` decimals: a value that rounds to zero is "zero".
function deltaSign(value: number, digits = 0): DeltaSign {
  if (Number(value.toFixed(digits)) === 0) return 'zero'
  return value > 0 ? 'positive' : 'negative'
}

export function Delta({ value, digits = 0, unit = '' }: { value: number; digits?: number; unit?: string }) {
  const sign = deltaSign(value, digits)
  return (
    <span className={`delta delta-${sign}`} data-sign={sign}>
      {signed(value, digits)}
      {unit && ` ${unit}`}
    </span>
  )
}

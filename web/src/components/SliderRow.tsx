import type { CSSProperties } from 'react'

export interface SliderRowProps {
  id: string
  label: string
  min: number
  max: number
  step: number
  value: number
  opening: number
  // text for a position on the track: level name, "4 years", "B2"; also the aria-valuetext
  valueText: (position: number) => string
  // shorter text drawn next to the label; defaults to valueText
  shortText?: (position: number) => string
  // position of the level the CV supports; null draws no tick
  tick?: number | null
  // the value is above what the CV shows (maroon track)
  above?: boolean
  notes?: string[]
  // drawn under a parent skill
  indent?: boolean
  hidden?: boolean
  onChange: (position: number) => void
}

export function SliderRow({
  id,
  label,
  min,
  max,
  step,
  value,
  opening,
  valueText,
  shortText = valueText,
  tick = null,
  above = false,
  notes = [],
  indent = false,
  hidden = false,
  onChange,
}: SliderRowProps) {
  const inputId = `slider-${id}`
  const span = max - min
  // the opening value may lie outside the slider range (experience above the maximum)
  const shown = Math.min(max, Math.max(min, value))
  const moved = value !== opening
  const classes = ['slider-row', moved && 'moved', above && 'above', indent && 'indent'].filter(Boolean).join(' ')
  const style = { '--fill': span > 0 ? (shown - min) / span : 0 } as CSSProperties
  return (
    <div className={classes} hidden={hidden} data-slider={id}>
      <div className="slider-head">
        <label htmlFor={inputId}>{label}</label>
        <span className="slider-value" title={valueText(value)}>
          {shortText(value)}
          {moved && <span className="was"> was {shortText(opening)}</span>}
        </span>
      </div>
      <div className="slider-track" style={style}>
        <input
          id={inputId}
          className="range"
          type="range"
          min={min}
          max={max}
          step={step}
          value={shown}
          aria-valuetext={valueText(value)}
          onChange={(e) => onChange(Number(e.currentTarget.value))}
        />
        {tick !== null && span > 0 && (
          <span
            className="cv-tick"
            style={{ '--at': (tick - min) / span } as CSSProperties}
            title={`CV shows: ${valueText(tick)}`}
            aria-hidden="true"
          />
        )}
      </div>
      {notes.map((n) => (
        <p key={n} className="slider-note">
          {n}
        </p>
      ))}
    </div>
  )
}

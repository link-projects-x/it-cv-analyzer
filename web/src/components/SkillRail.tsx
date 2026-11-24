import { useId, useState, type ReactNode } from 'react'
import { groupLabel, shownSliderIds, type RailGroup } from '../rail'
import type { SkillSlider } from '../visibility'

export interface SkillRailProps {
  groups: RailGroup[]
  // ids expanded by default (largest effect)
  top: string[]
  // ids moved from the opening level; they stay expanded
  moved: string[]
  renderSlider: (slider: SkillSlider, opts: { indent: boolean; hidden: boolean }) => ReactNode
}

// Skill sliders grouped by skills.json group. Every slider stays in the DOM; collapsed and
// filtered-out rows get the `hidden` attribute.
export function SkillRail({ groups, top, moved, renderSlider }: SkillRailProps) {
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(false)
  const searchId = useId()
  const listId = useId()

  const all = groups.flatMap((g) => g.items.map((i) => i.slider))
  const shown = shownSliderIds(all, { query, showAll, top, moved })
  const searching = query.trim() !== ''

  return (
    <div className="skill-rail">
      <div className="rail-search">
        <label htmlFor={searchId} className="sr-only">
          Search skills
        </label>
        <input
          id={searchId}
          type="search"
          className="search"
          placeholder={`Search ${all.length} skills`}
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
        />
      </div>
      <p className="rail-status" aria-live="polite">
        {searching
          ? `${shown.size} of ${all.length} skills match`
          : showAll
            ? `All ${all.length} skills`
            : `${shown.size} skills with the largest effect`}
      </p>
      <div id={listId}>
        {groups.map((g) => {
          const visible = g.items.some((i) => shown.has(i.slider.id))
          return (
            <section key={g.id} className="rail-group" hidden={!visible} aria-label={groupLabel(g.id)}>
              <h3 className="rail-group-h">{groupLabel(g.id)}</h3>
              {g.items.map((i) =>
                renderSlider(i.slider, {
                  indent: i.parent !== null && shown.has(i.parent),
                  hidden: !shown.has(i.slider.id),
                }),
              )}
            </section>
          )
        })}
      </div>
      {searching && shown.size === 0 && <p className="muted">No skill slider matches “{query.trim()}”.</p>}
      {!searching && all.length > top.length && (
        <button
          type="button"
          className="btn btn-ghost show-all"
          aria-expanded={showAll}
          aria-controls={listId}
          onClick={() => setShowAll((v) => !v)}
        >
          {showAll ? `Show top ${top.length}` : `Show all ${all.length}`}
        </button>
      )}
    </div>
  )
}

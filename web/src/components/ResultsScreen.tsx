import { useEffect, useMemo, useRef, useState } from 'react'
import { COVERAGE_CONFIG, levelName, shortLevelName, skillName } from '../contracts'
import { effectiveLevels } from '../coverage'
import { hints } from '../hints'
import { groupSliders, sliderEffects, topSliderIds } from '../rail'
import { requirementChecks } from '../requirements'
import {
  coverages,
  currentProfile,
  cvSupportedLevel,
  cvTick,
  dragSkill,
  english,
  experienceYears,
  initialState,
  isTouched,
  openingExperiencePosition,
  openingProfile,
  openingSkillLevel,
  reset,
  setEnglish,
  setExperience,
  skillLevel,
} from '../state'
import { openingSummary, summary, summaryDelta } from '../summary'
import type { Cefr, MatchResponse } from '../types'
import type { VacancyRow } from '../vacancies'
import { visibleSkillSliders } from '../visibility'
import { marketRows } from '../market'
import { improvementPlan } from '../plan'
import { HintList } from './HintList'
import { SkillRail } from './SkillRail'
import { SliderRow } from './SliderRow'
import { Headline } from './Headline'
import { MarketTable } from './MarketTable'
import { ThemeToggle } from './ThemeToggle'
import { VacancyList, type VacancyDetails } from './VacancyList'

const SL = COVERAGE_CONFIG.sliders

export function ResultsScreen({
  response,
  onNewCv,
  onCategoryChange,
}: {
  response: MatchResponse
  onNewCv?: () => void
  onCategoryChange?: (category: string) => void
}) {
  const [state, setState] = useState(() => initialState(response))
  const [sheetOpen, setSheetOpen] = useState(false)
  const closeRef = useRef<HTMLButtonElement>(null)

  const vacancies = useMemo(() => response.vacancies.map((v) => v.vacancy), [response])
  const opening = useMemo(() => {
    const s = initialState(response)
    return { results: coverages(s, vacancies), summary: openingSummary(s, vacancies, response.salary) }
  }, [response, vacancies])
  const rail = useMemo(() => {
    const profile = openingProfile(initialState(response))
    const sliders = visibleSkillSliders(profile, vacancies)
    const effects = sliderEffects(profile, vacancies, sliders)
    return { sliders, groups: groupSliders(sliders, effects), top: topSliderIds(sliders, effects) }
  }, [response, vacancies])

  useEffect(() => {
    if (sheetOpen) closeRef.current?.focus()
  }, [sheetOpen])

  const results = coverages(state, vacancies)
  const current = summary(state, vacancies, response.salary)
  const delta = summaryDelta(current, opening.summary)
  const touched = isTouched(state)
  const profile = currentProfile(state)
  const effective = effectiveLevels(profile.skills)
  const topHints = hints(state, vacancies, response.salary, rail.sliders.map((s) => s.id))
  const moved = Object.keys(state.touched.skills)
  const marketSource = response.marketVacancies ?? vacancies
  const market = marketRows(marketSource, profile.skills)
  const plan = useMemo(
    () => improvementPlan(initialState(response), vacancies, response.salary, rail.sliders.map((s) => s.id)),
    [response, vacancies, rail],
  )

  // English positions: the CEFR values from coverage.json, plus "not stated" first when the CV has none.
  const englishValues: (Cefr | null)[] = [
    ...(state.opening.english === null ? [null] : []),
    ...(SL.english.values as Cefr[]),
  ]
  const englishText = (i: number) => englishValues[i] ?? 'not stated'

  const rows: VacancyRow[] = response.vacancies.map((v, i) => ({
    id: v.vacancy.id,
    url: v.vacancy.url,
    title: v.vacancy.title,
    company: v.vacancy.company,
    similarity: v.similarity,
    coverage: results[i]?.coverage ?? null,
    openingCoverage: opening.results[i]?.coverage ?? null,
    fits: results[i]?.fits ?? false,
  }))
  const details: Record<string, VacancyDetails> = Object.fromEntries(
    response.vacancies.map((v) => [
      v.vacancy.id,
      { location: v.vacancy.location ?? null, checks: requirementChecks(profile, v.vacancy) },
    ]),
  )

  return (
    <div className="page">
      <header className="page-head">
        <div>
          {response.category ? (
            <>
              <h1>Your CV against {response.category} vacancies</h1>
              <p className="page-sub">
                Category picked from your CV. Your CV was read in this browser and not sent anywhere.
              </p>
              {onCategoryChange && response.categories && (
                <label className="category-pick">
                  <span>Category</span>
                  <select value={response.category} onChange={(e) => onCategoryChange(e.target.value)}>
                    {response.categories.map((c) => (
                      <option key={c.name} value={c.name}>
                        {c.name} ({c.count})
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </>
          ) : (
            <>
              <h1>CV vs DOU AI/ML vacancies</h1>
              <p className="page-sub">
                Example data from contracts/examples/match-response.example.json; nothing is sent anywhere.
              </p>
            </>
          )}
        </div>
        <div className="page-actions">
          {onNewCv && (
            <button type="button" className="btn btn-pill" onClick={onNewCv}>
              New CV
            </button>
          )}
          <ThemeToggle />
        </div>
      </header>

      {(response.undated?.length || response.grade) && (
        <div className="notice" role="note">
          {response.grade && (
            <p>
              Vacancies for your grade and one grade around it: CV reads as <strong>{response.grade}</strong>.
            </p>
          )}
          {response.undated && response.undated.length > 0 && (
            <p>
              <strong>
                {response.undated.length} {response.undated.length === 1 ? 'skill has' : 'skills have'} no dates
              </strong>{' '}
              in your job descriptions, so their years are set to your total experience (
              {levelName(response.profile.experience_years >= 10 ? 10 : Math.round(response.profile.experience_years * 2) / 2)}
              ). Check those sliders: {response.undated.slice(0, 10).map(skillName).join(', ')}
              {response.undated.length > 10 ? `, and ${response.undated.length - 10} more` : ''}.
            </p>
          )}
        </div>
      )}

      <p className="sr-only" data-testid="summary" aria-live="polite">
        Fits: <strong>{current.fits}</strong> of {vacancies.length} vacancies · mean coverage{' '}
        {(current.mean * 100).toFixed(1)}%
      </p>

      <div className="results">
        <main className="results-main">
          <Headline current={current} delta={delta} touched={touched} plan={plan} modelVersion={response.salary.model_version} />
          <MarketTable rows={market} total={marketSource.length} />
          <HintList hints={topHints} />
          <VacancyList rows={rows} details={details} showDelta={touched} />
        </main>

        <aside
          id="profile-rail"
          className={sheetOpen ? 'rail open' : 'rail'}
          aria-labelledby="sliders-h"
          onKeyDown={(e) => {
            if (e.key === 'Escape' && sheetOpen) setSheetOpen(false)
          }}
        >
          <div className="rail-head">
            <h2 id="sliders-h" className="section-h">
              Profile
            </h2>
            <div className="rail-actions">
              <button type="button" className="btn btn-pill" onClick={() => setState(reset)} disabled={!touched}>
                Reset
              </button>
              <button
                ref={closeRef}
                type="button"
                className="btn btn-ghost sheet-close"
                onClick={() => setSheetOpen(false)}
              >
                Close
              </button>
            </div>
          </div>

          <div className="rail-pinned">
            <SliderRow
              id="experience"
              label="Experience"
              min={SL.experience_years.min}
              max={SL.experience_years.max}
              step={SL.experience_years.step}
              value={experienceYears(state)}
              opening={openingExperiencePosition(state)}
              valueText={(n) => `${n} years`}
              onChange={(n) => setState((s) => setExperience(s, n))}
            />
            <SliderRow
              id="english"
              label="English"
              min={0}
              max={englishValues.length - 1}
              step={1}
              value={englishValues.indexOf(english(state))}
              opening={englishValues.indexOf(state.opening.english)}
              valueText={englishText}
              onChange={(i) => setState((s) => setEnglish(s, englishValues[i] ?? null))}
            />
          </div>

          <h3 className="rail-sub">Skills that change coverage of the loaded vacancies ({rail.sliders.length})</h3>
          <SkillRail
            groups={rail.groups}
            top={rail.top}
            moved={moved}
            renderSlider={(sk, { indent, hidden }) => {
              const value = skillLevel(state, sk.id)
              const above = value !== openingSkillLevel(state, sk.id) && value > cvSupportedLevel(state, sk.id)
              const notes: string[] = []
              if (above) notes.push('Level is above what the CV shows.')
              const eff = effective[sk.id] ?? 0
              if (eff > value) notes.push(`Counts as "${levelName(eff)}" through a sub-skill.`)
              return (
                <SliderRow
                  key={sk.id}
                  id={sk.id}
                  label={sk.name}
                  min={SL.skill.min}
                  max={SL.skill.max}
                  step={SL.skill.step}
                  value={value}
                  opening={openingSkillLevel(state, sk.id)}
                  valueText={levelName}
                  shortText={shortLevelName}
                  tick={cvTick(state, sk.id)}
                  above={above}
                  notes={notes}
                  indent={indent}
                  hidden={hidden}
                  onChange={(n) => setState((s) => dragSkill(s, sk.id, n))}
                />
              )
            }}
          />
        </aside>
      </div>

      <button
        type="button"
        className="btn btn-primary sheet-toggle"
        aria-controls="profile-rail"
        aria-expanded={sheetOpen}
        onClick={() => setSheetOpen((v) => !v)}
      >
        {sheetOpen ? 'Hide profile sliders' : `Adjust profile (${rail.sliders.length + 2} sliders)`}
      </button>
      {sheetOpen && <div className="sheet-backdrop" aria-hidden="true" onClick={() => setSheetOpen(false)} />}
    </div>
  )
}

// Slider rail layout: which skill sliders are expanded, how they are grouped, and search.
// The slider set itself comes from visibility.ts; this module only orders and filters it.
import { COVERAGE_CONFIG, SKILLS } from './contracts'
import { coverage } from './coverage'
import type { CoverageProfile, CoverageVacancy, SkillDef } from './types'
import type { SkillSlider } from './visibility'

// Effect of a skill slider: sum over the loaded vacancies of the coverage change between the
// slider minimum and maximum, other skills at `profile` (the page passes the opening profile).
export function sliderEffects(
  profile: CoverageProfile,
  vacancies: CoverageVacancy[],
  sliders: SkillSlider[],
  catalog: SkillDef[] = SKILLS,
): Record<string, number> {
  const { min, max } = COVERAGE_CONFIG.sliders.skill
  const out: Record<string, number> = {}
  for (const s of sliders) {
    const low = { ...profile, skills: { ...profile.skills, [s.id]: min } }
    const high = { ...profile, skills: { ...profile.skills, [s.id]: max } }
    let sum = 0
    for (const v of vacancies) {
      const a = coverage(low, v, COVERAGE_CONFIG, catalog).coverage
      const b = coverage(high, v, COVERAGE_CONFIG, catalog).coverage
      if (a !== null && b !== null) sum += Math.abs(b - a)
    }
    out[s.id] = sum
  }
  return out
}

// The `n` sliders with the largest effect. Ties keep the order of `sliders`.
export function topSliderIds(sliders: SkillSlider[], effects: Record<string, number>, n = 8): string[] {
  return sliders
    .map((s, i) => ({ id: s.id, i, e: effects[s.id] ?? 0 }))
    .sort((a, b) => b.e - a.e || a.i - b.i)
    .slice(0, n)
    .map((x) => x.id)
}

export interface RailItem {
  slider: SkillSlider
  // id of the parent skill when that parent also has a slider in the same group
  parent: string | null
}

export interface RailGroup {
  id: string
  items: RailItem[]
}

// Groups by skills.json `group`; a child skill follows its parent. Groups are ordered by the
// largest effect among their sliders, then by first appearance in skills.json. Inside a group,
// top-level sliders are ordered by effect, then by the order of `sliders`.
export function groupSliders(
  sliders: SkillSlider[],
  effects: Record<string, number>,
  catalog: SkillDef[] = SKILLS,
): RailGroup[] {
  const def = new Map(catalog.map((s) => [s.id, s]))
  const groupOrder = [...new Set(catalog.map((s) => s.group))]
  const order = new Map(sliders.map((s, i) => [s.id, i]))
  const byEffect = (a: SkillSlider, b: SkillSlider) =>
    (effects[b.id] ?? 0) - (effects[a.id] ?? 0) || (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0)

  const groups = new Map<string, SkillSlider[]>()
  for (const s of sliders) {
    const g = def.get(s.id)?.group ?? 'other'
    groups.set(g, [...(groups.get(g) ?? []), s])
  }

  const out: RailGroup[] = []
  for (const [id, members] of groups) {
    const ids = new Set(members.map((m) => m.id))
    const parentOf = (s: SkillSlider) => {
      const p = def.get(s.id)?.parent
      return p !== undefined && ids.has(p) ? p : null
    }
    const roots = members.filter((m) => parentOf(m) === null).sort(byEffect)
    const items: RailItem[] = []
    const place = (s: SkillSlider, parent: string | null) => {
      items.push({ slider: s, parent })
      for (const child of members.filter((m) => parentOf(m) === s.id).sort(byEffect)) place(child, s.id)
    }
    for (const r of roots) place(r, null)
    out.push({ id, items })
  }

  const maxEffect = (g: RailGroup) => Math.max(...g.items.map((i) => effects[i.slider.id] ?? 0))
  const rank = (id: string) => {
    const i = groupOrder.indexOf(id)
    return i === -1 ? groupOrder.length : i
  }
  return out.sort((a, b) => maxEffect(b) - maxEffect(a) || rank(a.id) - rank(b.id))
}

// Case-insensitive substring match on the skill name and its skills.json aliases
// ("gcp" finds "Google Cloud").
export function matchesSearch(names: string[], query: string): boolean {
  const q = query.trim().toLocaleLowerCase('en')
  return q === '' || names.some((n) => n.toLocaleLowerCase('en').includes(q))
}

export interface RailFilter {
  query: string
  showAll: boolean
  top: string[]
  // sliders moved from their opening level stay expanded
  moved: string[]
}

// Ids of the skill sliders drawn expanded. A search shows every match, whatever `showAll` is.
export function shownSliderIds(sliders: SkillSlider[], f: RailFilter, catalog: SkillDef[] = SKILLS): Set<string> {
  if (f.query.trim() !== '') {
    const aliases = new Map(catalog.map((s) => [s.id, s.aliases]))
    const names = (s: SkillSlider) => [s.name, ...(aliases.get(s.id) ?? [])]
    return new Set(sliders.filter((s) => matchesSearch(names(s), f.query)).map((s) => s.id))
  }
  if (f.showAll) return new Set(sliders.map((s) => s.id))
  return new Set([...f.top, ...f.moved])
}

export const GROUP_LABELS: Record<string, string> = {
  language: 'Languages',
  backend: 'Backend',
  data: 'Data',
  'data-eng': 'Data engineering',
  frontend: 'Frontend',
  devops: 'DevOps',
  cloud: 'Cloud',
  llm: 'LLM',
  ml: 'Machine learning',
  cv: 'Computer vision',
  'nlp-speech': 'NLP and speech',
}

export function groupLabel(id: string): string {
  return GROUP_LABELS[id] ?? id
}

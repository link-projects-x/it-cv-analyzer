// CV text -> profile, in the browser, without an LLM: skills by skills.json aliases, experience from date
// ranges or "N years", English from CEFR codes or level words, seniority from the first lines.
// Skill years: the dated job entries whose text mentions the skill, overlaps merged. A skill the CV names only
// outside dated entries (a skills list) gets the CV's total experience and dated: false; the page tells the
// person how many skills have no dates so they check those sliders. Assumption: a listed skill was used for the
// whole career; the CV text does not say.
import { COVERAGE_CONFIG, SKILLS } from '../contracts'

const SKILL_MAX = COVERAGE_CONFIG.sliders.skill.max
import type { Cefr, Profile, SkillDef } from '../types'

export type Seniority = 'intern' | 'junior' | 'middle' | 'senior' | 'lead' | 'unknown'

export interface CvSkill {
  id: string
  /** years with the skill */
  level: number
  evidence: string | null
  /** true when the years come from dated job entries; false when the skill is only listed */
  dated: boolean
}

export interface CvProfile extends Profile {
  skills: CvSkill[]
  seniority: Seniority
  /** skill ID of the most mentioned programming language, or null */
  primaryLanguage: string | null
}

const LANGUAGE_IDS = [
  'python', 'typescript', 'javascript', 'java', 'c-sharp', 'php', 'sql', 'cpp', 'kotlin', 'swift', 'golang',
  'bash', 'flutter', 'ruby', 'c-lang', 'rust', 'scala', 'powershell',
]

const EVIDENCE_CHARS = 120

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

interface Matcher {
  id: string
  pattern: RegExp
}

// Aliases of 1-2 letters ("go", "ts", "c") match only as written in the vocabulary's display case
// ("Go", "TS", "C") to keep "go to" and similar words out; longer aliases match case-insensitively.
// Aliases that are also plain English words match in capitals only ("REST", not "the rest").
const UPPERCASE_ONLY = new Set(['rest'])

export function buildMatchers(catalog: SkillDef[] = SKILLS): Matcher[] {
  const out: Matcher[] = []
  for (const skill of catalog) {
    const aliases = new Set([...skill.aliases, skill.name.toLowerCase()])
    const parts: string[] = []
    const shortParts: string[] = []
    for (const alias of aliases) {
      const a = alias.trim()
      if (!a) continue
      if (UPPERCASE_ONLY.has(a)) {
        shortParts.push(escapeRegex(a.toUpperCase()))
        continue
      }
      if (a.replace(/[^a-z0-9]/g, '').length <= 2 && !/[#+.]/.test(a)) {
        if (a.length === 1) continue
        shortParts.push(escapeRegex(a.toUpperCase()), escapeRegex(a.charAt(0).toUpperCase() + a.slice(1)))
      } else {
        parts.push(escapeRegex(a))
      }
    }
    // Word edges: no letter, digit, "+" or "#" right before or after ("c++" is not "c", "node.js" is not "node").
    const edge = (body: string) => `(?<![\\p{L}\\p{N}+#])(?:${body})(?![\\p{L}\\p{N}+#]|\\.[\\p{L}\\p{N}])`
    if (parts.length) out.push({ id: skill.id, pattern: new RegExp(edge(parts.join('|')), 'giu') })
    if (shortParts.length) out.push({ id: skill.id, pattern: new RegExp(edge(shortParts.join('|')), 'gu') })
  }
  return out
}

let defaultMatchers: Matcher[] | null = null

/** Skill ID -> positions of its mentions in the text. */
export function skillMentions(text: string, matchers?: Matcher[]): Map<string, number[]> {
  const list = matchers ?? (defaultMatchers ??= buildMatchers())
  const hits = new Map<string, number[]>()
  for (const { id, pattern } of list) {
    pattern.lastIndex = 0
    for (const m of text.matchAll(pattern)) hits.set(id, [...(hits.get(id) ?? []), m.index ?? 0])
  }
  return hits
}

/** Years rounded to the slider step (half a year) and capped at the slider maximum. */
function sliderYears(years: number): number {
  return Math.min(SKILL_MAX, Math.round(years * 2) / 2)
}

export function detectSkills(text: string, now = new Date(), undatedYears = 0, matchers?: Matcher[]): CvSkill[] {
  const mentions = skillMentions(text, matchers)
  const blocks = jobBlocks(text, now)
  const out: CvSkill[] = []
  for (const [id, positions] of mentions) {
    const spans = blocks.filter((b) => positions.some((p) => p >= b.from && p < b.to)).map((b) => b.span)
    const years = spans.length ? sliderYears(mergedMonths(spans) / 12) : 0
    out.push({
      id,
      level: years > 0 ? years : sliderYears(undatedYears),
      evidence: snippet(text, Math.min(...positions)),
      dated: years > 0,
    })
  }
  return out
}

function snippet(text: string, at: number): string {
  const start = Math.max(0, at - 40)
  return text.slice(start, start + EVIDENCE_CHARS).replace(/\s+/g, ' ').trim()
}

const MONTHS: Record<string, number> = {
  jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11,
  січ: 0, лют: 1, бер: 2, кві: 3, тра: 4, чер: 5, лип: 6, сер: 7, вер: 8, жов: 9, лис: 10, гру: 11,
}
const MONTH = '([a-zа-яії]{3,9}\\.?|\\d{1,2})?'
const RANGE = new RegExp(
  `${MONTH}[\\s/.]*((?:19|20)\\d{2})\\s*(?:-|–|—|to|до|по)\\s*(?:(present|now|current|today|теперішній час|дотепер|сьогодні|зараз)|${MONTH}[\\s/.]*((?:19|20)\\d{2}))`,
  'giu',
)

function monthIndex(raw: string | undefined): number | null {
  if (!raw) return null
  const s = raw.toLowerCase().replace('.', '')
  if (/^\d+$/.test(s)) {
    const n = Number(s)
    return n >= 1 && n <= 12 ? n - 1 : null
  }
  return MONTHS[s.slice(0, 3)] ?? null
}

/** Total years covered by date ranges ("Jun 2019 — Feb 2022", "03/2022 - Present"), overlaps merged. */
const EDUCATION = /^\s*(education|освіта|образование|courses|курси|certifications?)\b/imu
const NEXT_SECTION = /^\s*(skills|languages|навички|мови|languages|projects|проєкти|experience|employment|досвід)\b/imu

const SECTION_END = /^\s*(skills|technical skills|languages|education|projects|certifications?|courses|навички|мови|освіта|проєкти|курси)\b/imu

interface JobBlock {
  /** text positions [from, to) of the entry: its date range up to the next range or section heading */
  from: number
  to: number
  /** months [start, end) */
  span: [number, number]
}

/** Dated job entries, education skipped. Positions refer to `text` itself. */
export function jobBlocks(text: string, now = new Date()): JobBlock[] {
  const nowM = now.getFullYear() * 12 + now.getMonth()
  const edu = text.search(EDUCATION)
  const eduEnd = edu < 0 ? -1 : (() => {
    const rest = text.slice(edu + 1)
    const end = rest.search(NEXT_SECTION)
    return end < 0 ? text.length : edu + 1 + end
  })()
  const matches = [...text.matchAll(RANGE)].filter((m) => edu < 0 || (m.index ?? 0) < edu || (m.index ?? 0) >= eduEnd)
  // When some ranges have months, year-only ranges are usually studies or side notes: skip them.
  const withMonths = matches.some((m) => monthIndex(m[1]) !== null)
  const kept = matches.filter((m) => !withMonths || monthIndex(m[1]) !== null)
  const blocks: JobBlock[] = []
  kept.forEach((m, i) => {
    const [, m1, y1, present, m2, y2] = m
    const start = Number(y1) * 12 + (monthIndex(m1) ?? 0)
    // The end month counts in full: "Feb 2022 — Mar 2022" is two months, "Present" includes this month.
    const end = present ? nowM + 1 : Number(y2) * 12 + (monthIndex(m2) ?? 11) + 1
    if (!(end > start && end <= nowM + 1 && start >= 1980 * 12)) return
    const from = m.index ?? 0
    const nextRange = kept[i + 1]?.index ?? text.length
    const afterRange = text.slice(from + m[0].length)
    const section = afterRange.search(SECTION_END)
    const sectionAt = section < 0 ? text.length : from + m[0].length + section
    const to = Math.min(nextRange, sectionAt, edu > from ? edu : text.length)
    blocks.push({ from, to, span: [start, end] })
  })
  return blocks
}

function mergedMonths(spans: [number, number][]): number {
  const sorted = [...spans].sort((a, b) => a[0] - b[0])
  let total = 0
  const first = sorted[0]
  if (!first) return 0
  let [curS, curE] = first
  for (const [s, e] of sorted.slice(1)) {
    if (s <= curE) curE = Math.max(curE, e)
    else {
      total += curE - curS
      ;[curS, curE] = [s, e]
    }
  }
  return total + (curE - curS)
}

export function experienceFromRanges(text: string, now = new Date()): number | null {
  const blocks = jobBlocks(text, now)
  if (!blocks.length) return null
  return Math.round((mergedMonths(blocks.map((b) => b.span)) / 12) * 10) / 10
}

/** The largest "N years" / "N+ років" in the text, e.g. "7 years of commercial experience". */
export function experienceFromYears(text: string): number | null {
  let best: number | null = null
  for (const m of text.matchAll(/(\d{1,2})(?:[.,]\d)?\s*\+?\s*(?:years?|yrs|років|роки|рік|лет|года|год)/giu)) {
    const n = Number(m[1])
    if (n <= 40) best = Math.max(best ?? 0, n)
  }
  return best
}

const ENGLISH_WORDS: [RegExp, Cefr][] = [
  [/\bnative\b|носій/iu, 'C2'],
  [/\bproficient\b|\bfluent\b|\badvanced\b|вільн/iu, 'C1'],
  [/upper[\s-]?intermediate/iu, 'B2'],
  [/pre[\s-]?intermediate/iu, 'A2'],
  [/\bintermediate\b/iu, 'B1'],
  [/\belementary\b|\bbeginner\b/iu, 'A1'],
]

export function detectEnglish(text: string): Cefr | null {
  // Only the words right after "English", up to the next language: in "English - Intermediate, Ukrainian -
  // Native" the "Native" belongs to Ukrainian. Also "English (B2)" and "B2 English" in one line.
  const after = text.match(/(?:english|англійськ\S*|английск\S*)\s*[-–—:(]?\s*([^,;|\n)]{0,40})/iu)?.[1] ?? ''
  const before = text.match(/\b([ABC][12])\b[^,;|\n]{0,15}(?:english|англ)/iu)?.[1] ?? ''
  const near = after + ' ' + before
  const cefr = near.match(/\b([ABC][12])\b/)
  if (cefr) return cefr[1] as Cefr
  for (const [re, level] of ENGLISH_WORDS) if (re.test(near)) return level
  return null
}

export function detectSeniority(text: string): Seniority {
  const head = text.slice(0, 400).toLowerCase()
  if (/\b(team ?lead|tech ?lead|lead)\b/.test(head)) return 'lead'
  if (/\b(senior|sr\.?)\b/.test(head)) return 'senior'
  if (/\b(middle|mid)\b/.test(head)) return 'middle'
  if (/\b(junior|jr\.?)\b/.test(head)) return 'junior'
  if (/\b(intern|trainee)\b/.test(head)) return 'intern'
  return 'unknown'
}

export function buildProfile(text: string, now = new Date()): CvProfile {
  const years = experienceFromRanges(text, now) ?? experienceFromYears(text) ?? 0
  const skills = detectSkills(text, now, years)
  // The most used language by dated years; listed-only skills rank below any dated one.
  const counts = new Map(skills.map((s) => [s.id, s.dated ? s.level + 100 : s.level]))
  const primaryLanguage =
    LANGUAGE_IDS.filter((id) => counts.has(id)).sort((a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0))[0] ?? null
  return {
    skills,
    experience_years: Math.min(50, years),
    english: detectEnglish(text),
    seniority: detectSeniority(text),
    primaryLanguage,
  }
}

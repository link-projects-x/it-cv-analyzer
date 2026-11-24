// MatchApi without a backend: the CV is read and matched in the browser against the static files built by
// scripts/build_static_data.py (public/data/vacancies.json, public/data/salary.json). Nothing leaves the page.
import type { JobStatus, MatchApi } from '../api/types'
import { COVERAGE_CONFIG } from '../contracts'
import { coverage } from '../coverage'
import type { Cefr, MatchResponse, Salary, Vacancy } from '../types'
import { buildProfile, type CvProfile } from './cvProfile'
import { CvReadError, extractText } from './cvText'

export interface StaticVacancy {
  category: string
  vacancy: Vacancy
}

export interface SalaryTable {
  model_version: string
  cefr: Cefr[]
  table: Record<string, { point: number[][]; low?: number[][]; high?: number[][] }>
}

export interface StaticData {
  vacancies: StaticVacancy[]
  salary: SalaryTable
}

export const TOP_VACANCIES = 50
/** Vacancies with fewer skill requirements are left out of matching: with no skills to compare,
 * coverage comes from experience and English alone (sales and management roles reached 100%). */
export const MIN_SKILL_REQUIREMENTS = 3

const SURVEY_CATEGORY: Record<string, string> = {
  'AI/ML': 'DS / AI / ML / Data Engineering',
  'Data Science': 'DS / AI / ML / Data Engineering',
  'Data Engineer': 'DS / AI / ML / Data Engineering',
  'Big Data': 'DS / AI / ML / Data Engineering',
  DevOps: 'DevOps & SRE',
  SysAdmin: 'DevOps & SRE',
  QA: 'QA',
}
const DEFAULT_SURVEY_CATEGORY = 'Software Engineering & Architecture'

const SURVEY_LANGUAGE: Record<string, string> = {
  python: 'Python', typescript: 'TypeScript', javascript: 'JavaScript', java: 'Java', 'c-sharp': 'C# / .NET',
  php: 'PHP', sql: 'SQL', cpp: 'C++', kotlin: 'Kotlin', swift: 'Swift', golang: 'Go', bash: 'Bash / Shell',
  flutter: 'Dart', ruby: 'Ruby', 'c-lang': 'C', rust: 'Rust', scala: 'Scala', powershell: 'PowerShell',
}

const SURVEY_TITLE: Record<string, string> = {
  intern: 'Intern/Trainee', junior: 'Junior', middle: 'Middle', senior: 'Senior', lead: 'Lead',
}

// The salary model's training mode for English (ml/salary/README.md); used when the CV states none.
const DEFAULT_ENGLISH: Cefr = 'B2'

// Title from experience when the CV states none. Cut points from the DOU salary survey, June 2026 (experience
// by title, after ml/salary filters): Intern p75 0.5; Junior p75 2.0 and Middle p25 3.0 (cut at 2.5 between
// them); Middle p75 5.0 = Senior p25 5.0.
function titleFor(p: CvProfile): string {
  const fromCv = SURVEY_TITLE[p.seniority]
  if (fromCv) return fromCv
  if (p.experience_years < 0.5) return 'Intern/Trainee'
  if (p.experience_years < 2.5) return 'Junior'
  if (p.experience_years < 5) return 'Middle'
  return 'Senior'
}

function coverageProfile(p: CvProfile) {
  return {
    skills: Object.fromEntries(p.skills.map((s) => [s.id, s.level])),
    experience_years: p.experience_years,
    english: p.english,
  }
}

/** The DOU category whose vacancies the CV covers best on average; ties go to the bigger category. */
type Scored = { cov: number; v: StaticVacancy }

const GRADES = ['intern', 'junior', 'middle', 'senior', 'lead', 'principal']
const TITLE_GRADE: Record<string, string> = {
  'Intern/Trainee': 'intern', Junior: 'junior', Middle: 'middle', Senior: 'senior', Lead: 'lead',
}

/** The CV's grade: stated in the CV, else from experience (titleFor). */
export function cvGrade(p: CvProfile): string {
  return TITLE_GRADE[titleFor(p)] ?? 'middle'
}

/** A vacancy within one grade of the CV, or with no grade stated. Without it a senior CV ranks junior and
 * intern vacancies first: they ask for fewer years, so their coverage is highest. */
export function gradeFits(cvGradeName: string, vacancySeniority: string | undefined): boolean {
  const v = GRADES.indexOf(vacancySeniority ?? 'unknown')
  if (v < 0) return true
  return Math.abs(v - GRADES.indexOf(cvGradeName)) <= 1
}

// Non-engineering roles that DOU files under IT categories (an "AI Delivery Manager" sits in AI/ML and lists AI
// skills, so the skill count does not drop it). A rule on title words, not a model: a title outside this list
// stays even when the role is not engineering.
const NON_ENGINEERING_TITLE =
  /\b(sales|business development|bizdev|account manager|account executive|delivery manager|project manager|product manager|product owner|recruit\w*|marketing|marketer|hr|talent acquisition|customer success|presale\w*)\b/i

export function isEngineeringTitle(title: string): boolean {
  return !NON_ENGINEERING_TITLE.test(title)
}

function scoreByCategory(p: CvProfile, all: StaticVacancy[]): Map<string, Scored[]> {
  const cp = coverageProfile(p)
  const grade = cvGrade(p)
  const by = new Map<string, Scored[]>()
  for (const v of all) {
    if (v.vacancy.requirements.length < MIN_SKILL_REQUIREMENTS) continue
    if (!gradeFits(grade, v.vacancy.seniority)) continue
    if (!isEngineeringTitle(v.vacancy.title)) continue
    const cov = coverage(cp, v.vacancy, COVERAGE_CONFIG).coverage ?? 0
    by.set(v.category, [...(by.get(v.category) ?? []), { cov, v }])
  }
  return by
}

export function pickCategory(p: CvProfile, all: StaticVacancy[]): { category: string; scored: Scored[] } {
  const by = scoreByCategory(p, all)
  let best = ''
  let bestScore = -1
  for (const [category, list] of by) {
    // Mean over the top 10 of the category, so a big category with many unrelated vacancies is not punished.
    const top = list.map((x) => x.cov).sort((a, b) => b - a).slice(0, 10)
    const score = top.reduce((a, b) => a + b, 0) / top.length
    if (score > bestScore + 1e-9 || (Math.abs(score - bestScore) <= 1e-9 && list.length > (by.get(best)?.length ?? 0))) {
      best = category
      bestScore = score
    }
  }
  return { category: best, scored: by.get(best) ?? [] }
}

export function salaryFor(p: CvProfile, category: string, table: SalaryTable): Salary {
  const surveyCategory = SURVEY_CATEGORY[category] ?? DEFAULT_SURVEY_CATEGORY
  const lang = (p.primaryLanguage && SURVEY_LANGUAGE[p.primaryLanguage]) || ''
  const entry =
    table.table[`${surveyCategory}|${titleFor(p)}|${lang}`] ?? table.table[`${surveyCategory}|${titleFor(p)}|`]
  if (!entry) throw new Error(`salary table has no entry for ${surveyCategory} / ${titleFor(p)}`)
  // Same rounding as the experience slider (contracts/README.md): nearest whole year, half up, 0..15.
  const exp = Math.min(15, Math.max(0, Math.floor(p.experience_years + 0.5)))
  const eng = table.cefr.indexOf(p.english ?? DEFAULT_ENGLISH)
  const row = (g: number[][] | undefined, e: number, l: number) => g?.[e]?.[l] ?? null
  const english: Partial<Record<Cefr, number>> = {}
  table.cefr.forEach((c, i) => (english[c] = row(entry.point, exp, i) ?? 0))
  const experience_years: Record<string, number> = {}
  entry.point.forEach((r, e) => (experience_years[String(e)] = r[eng] ?? 0))
  return {
    currency: 'USD',
    period: 'month',
    point: row(entry.point, exp, eng) ?? 0,
    low: row(entry.low, exp, eng),
    high: row(entry.high, exp, eng),
    model_version: table.model_version,
    grid: { english, experience_years, company_type: {}, domains: {} },
  }
}

export function matchLocally(p: CvProfile, data: StaticData, forced?: string): MatchResponse & { category: string } {
  const by = scoreByCategory(p, data.vacancies)
  const category = forced && by.has(forced) ? forced : pickCategory(p, data.vacancies).category
  const scored = by.get(category) ?? []
  const top = [...scored].sort((a, b) => b.cov - a.cov).slice(0, TOP_VACANCIES)
  const categories = [...by.entries()]
    .map(([name, list]) => ({ name, count: list.length }))
    .sort((a, b) => a.name.localeCompare(b.name))
  return {
    schema_version: '1.0',
    category,
    categories,
    rematch: (next: string) => matchLocally(p, data, next),
    undated: p.skills.filter((s) => !s.dated).map((s) => s.id),
    grade: cvGrade(p),
    marketVacancies: scored.map((x) => x.v.vacancy),
    profile: { skills: p.skills, experience_years: p.experience_years, english: p.english },
    vacancies: top.map(({ cov, v }) => ({ similarity: cov, vacancy: v.vacancy })),
    salary: salaryFor(p, category, data.salary),
  }
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}${path}`)
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return (await res.json()) as T
}

let dataPromise: Promise<StaticData> | null = null

export function loadStaticData(): Promise<StaticData> {
  dataPromise ??= Promise.all([
    fetchJson<StaticVacancy[]>('data/vacancies.json'),
    fetchJson<SalaryTable>('data/salary.json'),
  ]).then(([vacancies, salary]) => ({ vacancies, salary }))
  dataPromise.catch(() => (dataPromise = null))
  return dataPromise
}

export function createLocalApi(load: () => Promise<StaticData> = loadStaticData): MatchApi {
  const jobs = new Map<string, Promise<JobStatus>>()
  const steps = new Map<string, number>()
  let counter = 0

  return {
    async uploadCv(file) {
      counter += 1
      const jobId = `local-${counter}`
      steps.set(jobId, 0)
      jobs.set(
        jobId,
        (async (): Promise<JobStatus> => {
          try {
            const [text, data] = await Promise.all([extractText(file), load()])
            return { state: 'done', result: matchLocally(buildProfile(text), data) }
          } catch (e) {
            const message = e instanceof CvReadError ? e.message : 'Could not analyse the CV in this browser.'
            return { state: 'failed', error: message }
          }
        })(),
      )
      return { jobId }
    },
    async getJob(jobId) {
      const job = jobs.get(jobId)
      if (!job) return { state: 'failed', error: `Unknown job ${jobId}.` }
      // Show "parsing" and "matching" once each, then the result as soon as it is ready.
      const step = steps.get(jobId) ?? 0
      steps.set(jobId, step + 1)
      if (step === 0) return { state: 'parsing' }
      if (step === 1) return { state: 'matching' }
      return job
    },
  }
}

import { describe, expect, it } from 'vitest'
import { buildProfile, detectEnglish, detectSeniority, detectSkills, experienceFromRanges, experienceFromYears } from './cvProfile'

const NOW = new Date('2026-11-21T00:00:00Z')

const CV = `Jane Doe, Senior Fullstack Developer
jane@example.com

SUMMARY
Senior Fullstack Developer with 7 years of commercial experience. React, TypeScript, Node.js, PostgreSQL.

EMPLOYMENT HISTORY
Dec 2024 — Present
Senior Fullstack Developer, MedTech - Remote
Built an AI chat with RAG on AWS Bedrock. React and TypeScript on the frontend.

Mar 2022 — Dec 2024
Senior Fullstack Developer, San Francisco
Node.js services, Docker, GitHub Actions.

Jun 2019 — Feb 2022
Frontend Developer
React, Redux, Jest.

SKILLS
Frontend: TypeScript, JavaScript, React, Next.js, Redux Toolkit
Backend: Node.js, NestJS, Python, Django, C#, C++
LANGUAGES
English - B2, Ukrainian - Native speaker
`

describe('detectSkills', () => {
  const ids = (text: string) => detectSkills(text).map((s) => s.id).sort()

  it('gives a skill the years of the dated jobs that mention it', () => {
    const skills = new Map(detectSkills(CV, NOW).map((s) => [s.id, s]))
    // React: Dec 2024 - Nov 2026 (24 months) and Jun 2019 - Feb 2022 (33 months) -> 4.75 -> 5 (half-year steps)
    expect(skills.get('react')).toMatchObject({ level: 5, dated: true })
    // AWS Bedrock: only the current job -> 2 years
    expect(skills.get('aws-bedrock')).toMatchObject({ level: 2, dated: true })
    // Node.js: only Mar 2022 - Dec 2024 (34 months) -> 2.8 -> 3; the summary line has no dates
    expect(skills.get('nodejs')).toMatchObject({ level: 3, dated: true })
    // Django is only in the skills list: the total experience passed in, not dated
    expect(skills.get('django')).toMatchObject({ level: 0, dated: false })
    expect(new Map(detectSkills(CV, NOW, 7.4).map((s) => [s.id, s.level])).get('django')).toBe(7.5)
    expect(skills.has('nextjs')).toBe(true)
    expect(skills.has('c-sharp')).toBe(true)
    expect(skills.has('cpp')).toBe(true)
  })

  it('keeps node.js, c++ and c# apart from node, c and c-lang', () => {
    expect(ids('Worked with C++ and C# only')).not.toContain('c-lang')
  })

  it('does not take "go" from ordinary text but takes "Go" the language', () => {
    expect(ids('ready to go to the office')).not.toContain('golang')
    expect(ids('Backend in Go and Python')).toContain('golang')
  })

  it('takes "REST" in capitals but not "the rest"', () => {
    expect(ids('Node.js, Docker, AWS, REST, PostgreSQL')).toContain('rest-api')
    expect(ids('the rest of the team')).not.toContain('rest-api')
  })

  it('stores a short evidence snippet', () => {
    const django = detectSkills(CV, NOW).find((s) => s.id === 'django')
    expect(django?.evidence).toContain('Django')
    expect((django?.evidence ?? '').length).toBeLessThanOrEqual(120)
  })
})

describe('experience', () => {
  it('sums date ranges and merges overlaps', () => {
    // Jun 2019 .. Nov 2026 inclusive, without gaps: 90 months
    expect(experienceFromRanges(CV, NOW)).toBe(7.5)
    expect(experienceFromRanges('2018 - 2020\n2019 - 2021', NOW)).toBe(4)
  })

  it('reads month numbers and Ukrainian "по теперішній час"', () => {
    expect(experienceFromRanges('03/2024 - теперішній час', NOW)).toBe(2.8)
  })

  it('skips the education section and year-only ranges when month ranges exist', () => {
    const text = 'EXPERIENCE\nJun 2019 — Feb 2022\nEDUCATION\n2015 — 2019\nUniversity\nSKILLS\nReact'
    expect(experienceFromRanges(text, NOW)).toBe(2.8)
    expect(experienceFromRanges('Mar 2020 - Mar 2021\nside project 2010 - 2012', NOW)).toBe(1.1)
  })

  it('falls back to "N years"', () => {
    expect(experienceFromYears('over 5+ years of experience, 3 years with Go')).toBe(5)
    expect(experienceFromYears('no numbers here')).toBeNull()
  })
})

describe('english and seniority', () => {
  it('reads CEFR codes and level words', () => {
    expect(detectEnglish(CV)).toBe('B2')
    expect(detectEnglish('English: Upper-Intermediate')).toBe('B2')
    expect(detectEnglish('Англійська — вільно')).toBe('C1')
    expect(detectEnglish('no language info')).toBeNull()
  })

  it('does not take the level of another language from the same line', () => {
    expect(detectEnglish('Languages: English - Intermediate, Ukrainian - Native')).toBe('B1')
    expect(detectEnglish('Ukrainian (native), English (upper-intermediate)')).toBe('B2')
    expect(detectEnglish('English: B1\nRussian: native')).toBe('B1')
  })

  it('takes seniority from the first lines', () => {
    expect(detectSeniority(CV)).toBe('senior')
    expect(detectSeniority('John, Junior QA Engineer')).toBe('junior')
  })
})

describe('buildProfile', () => {
  it('puts it together', () => {
    const p = buildProfile(CV, NOW)
    expect(p.experience_years).toBe(7.5)
    expect(p.skills.find((s) => s.id === 'django')).toMatchObject({ level: 7.5, dated: false })
    expect(p.english).toBe('B2')
    expect(p.seniority).toBe('senior')
    expect(p.primaryLanguage).not.toBeNull()
  })
})

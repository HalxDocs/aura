import { describe, it, expect } from 'vitest'
import {
  cleanSkills,
  isBlankEducation,
  isBlankExperience,
  mergeParsedIntoProfile,
  parsedHasContent,
  type ProfileFormState,
} from '@/lib/profile-utils'
import type { EducationEntry, ExperienceEntry, ParsedResumeProfile } from '@/api/client'

const emptyForm = (): ProfileFormState => ({
  headline: '',
  location: '',
  summary: '',
  skills: [],
  experience: [],
  education: [],
  linkedin_url: null,
  github_url: null,
  portfolio_url: null,
})

const parsed = (over: Partial<ParsedResumeProfile> = {}): ParsedResumeProfile => ({
  headline: 'Backend Engineer',
  location: 'Berlin',
  summary: 'Ships things.',
  skills: ['Python', 'Go'],
  experience: [{ title: 'SWE', company: 'Acme', start: '2020', end: '', description: '' }],
  education: [{ school: 'TU', degree: 'MSc', field: 'CS', start: '', end: '' }],
  linkedin_url: 'https://linkedin.com/in/x',
  github_url: null,
  portfolio_url: null,
  ...over,
})

describe('cleanSkills', () => {
  it('trims, dedupes case-insensitively, and drops empties', () => {
    expect(cleanSkills([' Python ', 'python', 'Go', '', 'GO', 'Rust'])).toEqual(['Python', 'Go', 'Rust'])
  })

  it('caps at 30 entries', () => {
    expect(cleanSkills(Array.from({ length: 40 }, (_, i) => `s${i}`)).length).toBe(30)
  })
})

describe('mergeParsedIntoProfile', () => {
  it('fills empty fields from the parse', () => {
    const merged = mergeParsedIntoProfile(emptyForm(), parsed())
    expect(merged.headline).toBe('Backend Engineer')
    expect(merged.skills).toEqual(['Python', 'Go'])
    expect(merged.experience[0].company).toBe('Acme')
    expect(merged.linkedin_url).toBe('https://linkedin.com/in/x')
  })

  it('never overwrites existing values', () => {
    const form: ProfileFormState = {
      ...emptyForm(),
      headline: 'My own headline',
      skills: ['Ruby'],
      linkedin_url: 'https://linkedin.com/in/mine',
    }
    const merged = mergeParsedIntoProfile(form, parsed())
    expect(merged.headline).toBe('My own headline')
    // Existing skills are kept and parsed ones are appended, not dropped.
    expect(merged.skills).toEqual(['Ruby', 'Python', 'Go'])
    expect(merged.linkedin_url).toBe('https://linkedin.com/in/mine')
    // …while still filling the untouched fields.
    expect(merged.location).toBe('Berlin')
    expect(merged.github_url).toBeNull()
  })

  it('appends parsed entries without duplicating saved rows', () => {
    const form: ProfileFormState = {
      ...emptyForm(),
      experience: [{ title: 'swe', company: 'ACME', start: '2019', end: '', description: 'kept' }],
      education: [{ school: 'TU', degree: 'MSc', field: 'CS', start: '', end: '' }],
    }
    const merged = mergeParsedIntoProfile(form, parsed())
    // Case-insensitive duplicate (same title+company) is skipped…
    expect(merged.experience).toHaveLength(1)
    expect(merged.experience[0].start).toBe('2019')
    // …and a genuinely new parsed entry is appended for review.
    const second = mergeParsedIntoProfile(form, parsed({
      experience: [
        { title: 'SWE', company: 'Acme', start: '', end: '', description: '' },
        { title: 'Intern', company: 'Globex', start: '', end: '', description: '' },
      ],
    }))
    expect(second.experience.map(e => e.company)).toEqual(['ACME', 'Globex'])
    expect(second.education).toHaveLength(1)
  })

  it('appends new skills case-insensitively and caps at 30', () => {
    const merged = mergeParsedIntoProfile(
      { ...emptyForm(), skills: ['Python', 'Go'] },
      parsed({ skills: ['go', 'Rust', ...Array.from({ length: 40 }, (_, i) => `s${i}`)] }),
    )
    expect(merged.skills[0]).toBe('Python')
    expect(merged.skills[1]).toBe('Go')
    expect(merged.skills).toContain('Rust')
    expect(merged.skills).not.toContain('go')
    expect(merged.skills).toHaveLength(30)
  })

  it('caps merged experience and education at 15 so the form can always be saved', () => {
    // 12 saved rows + 6 new parsed rows would exceed the backend's cap of 15.
    const saved = (n: number): ExperienceEntry[] =>
      Array.from({ length: n }, (_, i) => ({ title: `t${i}`, company: `c${i}`, start: '', end: '', description: '' }))
    const form: ProfileFormState = { ...emptyForm(), experience: saved(12) }
    const merged = mergeParsedIntoProfile(form, parsed({
      experience: Array.from({ length: 6 }, (_, i) => ({ title: `new${i}`, company: `nc${i}`, start: '', end: '', description: '' })),
    }))
    expect(merged.experience).toHaveLength(15)
    // Saved rows come first; parsed ones fill the remaining slots.
    expect(merged.experience[0].company).toBe('c0')
    expect(merged.experience[14].company).toBe('nc2')

    const eduSaved = (n: number): EducationEntry[] =>
      Array.from({ length: n }, (_, i) => ({ school: `s${i}`, degree: '', field: '', start: '', end: '' }))
    const eduForm: ProfileFormState = { ...emptyForm(), education: eduSaved(15) }
    const eduMerged = mergeParsedIntoProfile(eduForm, parsed({
      education: [{ school: 'Extra U', degree: '', field: '', start: '', end: '' }],
    }))
    expect(eduMerged.education).toHaveLength(15)
    expect(eduMerged.education.some(e => e.school === 'Extra U')).toBe(false)
  })

  it('treats whitespace-only current values as empty', () => {
    const merged = mergeParsedIntoProfile({ ...emptyForm(), headline: '   ' }, parsed())
    expect(merged.headline).toBe('Backend Engineer')
  })

  it('does not mutate the inputs', () => {
    const form = emptyForm()
    const p = parsed()
    mergeParsedIntoProfile(form, p)
    expect(form.headline).toBe('')
    expect(p.skills).toEqual(['Python', 'Go'])
  })
})

describe('parsedHasContent', () => {
  it('is false for an empty parse', () => {
    expect(parsedHasContent(parsed({
      headline: null, location: null, summary: null, skills: [],
      experience: [], education: [], linkedin_url: null,
    }))).toBe(false)
  })

  it('is true when only skills were found', () => {
    expect(parsedHasContent(parsed({
      headline: null, location: null, summary: null, skills: ['Go'],
      experience: [], education: [], linkedin_url: null,
    }))).toBe(true)
  })
})

describe('isBlankExperience / isBlankEducation', () => {
  const blankExperience = { title: '', company: '', start: '', end: '', description: '' }
  const blankEducation = { school: '', degree: '', field: '', start: '', end: '' }

  it('treats fully empty rows as blank', () => {
    expect(isBlankExperience(blankExperience)).toBe(true)
    expect(isBlankEducation(blankEducation)).toBe(true)
  })

  it('whitespace-only rows count as blank', () => {
    expect(isBlankExperience({ ...blankExperience, title: '   ' })).toBe(true)
    expect(isBlankEducation({ ...blankEducation, school: '  ' })).toBe(true)
  })

  it('any content makes a row non-blank', () => {
    expect(isBlankExperience({ ...blankExperience, start: '2020' })).toBe(false)
    expect(isBlankExperience({ ...blankExperience, title: 'SWE' })).toBe(false)
    expect(isBlankEducation({ ...blankEducation, degree: 'MSc' })).toBe(false)
  })
})

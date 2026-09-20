import type { CandidateProfile, EducationEntry, ExperienceEntry, ParsedResumeProfile } from '@/api/client'

export type ProfileFormState = Omit<CandidateProfile, 'resume_stored' | 'resume_uploaded_at'>

const MAX_SKILLS = 30
// Mirrors the backend's CandidateProfileIn list caps — saving more would 422.
const MAX_ENTRIES = 15

/**
 * A row the user left completely blank. Blank rows are dropped on save rather
 * than sent (the backend requires a title/company, resp. a school, and would
 * reject the whole profile with a 422).
 */
export function isBlankExperience(entry: ExperienceEntry): boolean {
  return !entry.title.trim() && !entry.company.trim() && !entry.start.trim() &&
    !entry.end.trim() && !entry.description.trim()
}

export function isBlankEducation(entry: EducationEntry): boolean {
  return !entry.school.trim() && !entry.degree.trim() && !entry.field.trim() &&
    !entry.start.trim() && !entry.end.trim()
}

/** Case-insensitive dedupe + hard cap for parsed skill lists. */
export function cleanSkills(skills: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of skills) {
    const skill = raw.trim().slice(0, 60)
    if (!skill) continue
    const key = skill.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(skill)
    if (out.length >= MAX_SKILLS) break
  }
  return out
}

const experienceKey = (e: ExperienceEntry) =>
  `${e.title.trim().toLowerCase()}\n${e.company.trim().toLowerCase()}`

const educationKey = (e: EducationEntry) =>
  `${e.school.trim().toLowerCase()}\n${e.degree.trim().toLowerCase()}`

/**
 * Keep every existing item and append the incoming ones that aren't already
 * present, capped at MAX_ENTRIES — the backend rejects lists beyond 15, so a
 * merged form that could never be saved is worse than a trimmed one.
 */
function appendEntries<T>(existing: T[], incoming: T[], keyOf: (item: T) => string): T[] {
  if (!incoming.length) return existing
  const seen = new Set(existing.map(keyOf))
  const out = [...existing]
  for (const item of incoming) {
    if (out.length >= MAX_ENTRIES) break
    if (seen.has(keyOf(item))) continue
    seen.add(keyOf(item))
    out.push(item)
  }
  return out
}

/** Like appendUnique for skills: case-insensitive, 60 chars, capped at MAX_SKILLS. */
function appendSkills(existing: string[], incoming: string[]): string[] {
  const seen = new Set(existing.map(skill => skill.trim().toLowerCase()))
  const out = [...existing]
  for (const raw of incoming) {
    if (out.length >= MAX_SKILLS) break
    const skill = raw.trim().slice(0, 60)
    if (!skill) continue
    const key = skill.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(skill)
  }
  return out
}

/**
 * Merge parsed resume values into the profile form for review.
 *
 * Single-value fields are only filled when empty, so re-uploading a resume
 * can never silently rewrite what the candidate already has. List fields
 * keep every saved row and skill and APPEND what the parser found, skipping
 * entries that duplicate a saved row (title+company, resp. school+degree,
 * case-insensitive) — everything new shows up in the form for review, and
 * the user still saves explicitly. Lists stop at the backend's caps (30
 * skills, 15 entries per list) so the merged form can always be saved.
 */
export function mergeParsedIntoProfile(form: ProfileFormState, parsed: ParsedResumeProfile): ProfileFormState {
  const keep = (current: string, parsedValue: string | null) =>
    current.trim() ? current : (parsedValue ?? '')

  const keepLink = (current: string | null, parsedValue: string | null) =>
    current && current.trim() ? current : parsedValue

  return {
    headline: keep(form.headline, parsed.headline),
    location: keep(form.location, parsed.location),
    summary: keep(form.summary, parsed.summary),
    skills: appendSkills(form.skills, cleanSkills(parsed.skills)),
    experience: appendEntries(form.experience, parsed.experience, experienceKey),
    education: appendEntries(form.education, parsed.education, educationKey),
    linkedin_url: keepLink(form.linkedin_url, parsed.linkedin_url),
    github_url: keepLink(form.github_url, parsed.github_url),
    portfolio_url: keepLink(form.portfolio_url, parsed.portfolio_url),
  }
}

/** Did the parser find anything worth telling the user about? */
export function parsedHasContent(parsed: ParsedResumeProfile): boolean {
  return !!(
    parsed.headline?.trim() ||
    parsed.location?.trim() ||
    parsed.summary?.trim() ||
    parsed.skills.length ||
    parsed.experience.length ||
    parsed.education.length ||
    parsed.linkedin_url ||
    parsed.github_url ||
    parsed.portfolio_url
  )
}

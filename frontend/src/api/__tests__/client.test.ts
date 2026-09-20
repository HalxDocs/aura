import { describe, it, expect } from 'vitest'
import { AxiosError, type AxiosResponse } from 'axios'
import { apiErrorMessage } from '@/api/client'

/** Build a real AxiosError carrying `data` as the response body. */
const axiosErrorWith = (data: unknown): AxiosError =>
  new AxiosError('Request failed', 'ERR_BAD_REQUEST', undefined, undefined, { data } as AxiosResponse)

describe('apiErrorMessage', () => {
  it('passes a string detail through', () => {
    const error = axiosErrorWith({ detail: 'Only PDF files are supported.' })
    expect(apiErrorMessage(error)).toBe('Only PDF files are supported.')
  })

  it('flattens the 422 handler payload into field messages', () => {
    const error = axiosErrorWith({
      detail: {
        message: 'Validation failed for the provided data.',
        errors: [
          { field: 'experience.0.title', message: 'Value error, Title and company must not be empty.' },
        ],
      },
    })
    expect(apiErrorMessage(error)).toBe(
      'Validation failed for the provided data. (experience.0.title: Title and company must not be empty.)'
    )
  })

  it('strips the pydantic "Value error, " prefix from validator messages', () => {
    const error = axiosErrorWith({
      detail: {
        message: 'Validation failed for the provided data.',
        errors: [{ field: 'github_url', message: 'Value error, Links must start with http:// or https://' }],
      },
    })
    expect(apiErrorMessage(error)).toContain('github_url: Links must start with http:// or https://')
    expect(apiErrorMessage(error)).not.toContain('Value error')
  })

  it('falls back when the body has nothing readable', () => {
    const error = axiosErrorWith({ something: 'else' })
    expect(apiErrorMessage(error, 'Could not save your profile.')).toBe('Could not save your profile.')
  })

  it('falls back for non-axios errors', () => {
    expect(apiErrorMessage(new Error('boom'), 'Could not save your profile.')).toBe('Could not save your profile.')
    expect(apiErrorMessage(null, 'fallback')).toBe('fallback')
  })

  it('surfaces slowapi 429 error bodies', () => {
    const error = axiosErrorWith({ error: 'Rate limit exceeded: 10 per 1 hour' })
    expect(apiErrorMessage(error)).toBe('Rate limit exceeded: 10 per 1 hour')
  })
})

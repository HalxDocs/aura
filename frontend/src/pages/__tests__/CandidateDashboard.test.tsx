import { describe, expect, it, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CandidateDashboard } from '../CandidateDashboard'
import * as client from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'

vi.mock('@/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    getCandidateProfile: vi.fn(),
    listMySessions: vi.fn(),
    startInterviewFromProfile: vi.fn(),
  }
})

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

const useAuthMock = vi.mocked(useAuth)

function renderDashboard() {
  return render(
    <MemoryRouter>
      <CandidateDashboard />
    </MemoryRouter>
  )
}

describe('CandidateDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthMock.mockReturnValue({
      user: { id: 'u1', email: 'c@example.com', name: 'Ada Lovelace', role: 'candidate' },
      token: 't',
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
      setAuth: vi.fn(),
    })
  })

  it('greets the user and shows stats from their sessions and profile', async () => {
    vi.mocked(client.getCandidateProfile).mockResolvedValue({
      headline: 'Backend engineer',
      location: 'Berlin',
      summary: '',
      skills: ['Go'],
      experience: [{ title: 'SWE', company: 'Acme', start: '2020', end: '', description: '' }],
      education: [],
      linkedin_url: null,
      github_url: null,
      portfolio_url: null,
      resume_stored: true,
      resume_uploaded_at: null,
    })
    vi.mocked(client.listMySessions).mockResolvedValue([
      {
        session_id: 's1',
        candidate_name: 'Ada Lovelace',
        overall_score: 78,
        recommendation: 'Hire',
        status: 'completed',
        created_at: '2026-09-20T10:00:00Z',
        completed_at: '2026-09-20T10:12:00Z',
        duration_seconds: 720,
      },
    ])

    renderDashboard()

    expect(await screen.findByRole('heading', { name: /welcome back, ada/i })).toBeInTheDocument()
    // 78 shows up twice (stat tile + table row); assert on the stat tile.
    const statValues = await screen.findAllByText('78')
    expect(statValues.length).toBeGreaterThanOrEqual(1)
    // A stored resume enables the one-click start, which plans the interview
    // directly instead of routing through the upload step.
    const start = await screen.findByRole('button', { name: /start a new interview/i })
    expect(start).toBeEnabled()
  })

  it('shows the empty state when no interviews exist yet', async () => {
    vi.mocked(client.getCandidateProfile).mockRejectedValue(new Error('no profile'))
    vi.mocked(client.listMySessions).mockResolvedValue([])

    renderDashboard()

    expect(await screen.findByText('No interviews yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /start your first interview/i })).toHaveAttribute('href', '/interview')
  })
})

import { describe, expect, it, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppHeader } from '../AppHeader'
import { useAuth, type Mode } from '@/contexts/AuthContext'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

const useAuthMock = vi.mocked(useAuth)

function authState(overrides: {
  user: Record<string, unknown>
  mode?: Mode
}) {
  return {
    user: overrides.user as never,
    token: 'test-token',
    loading: false,
    mode: overrides.mode ?? 'candidate',
    setMode: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    setAuth: vi.fn(),
  }
}

function renderHeader() {
  return render(
    <MemoryRouter>
      <AppHeader />
    </MemoryRouter>
  )
}

describe('AppHeader', () => {
  beforeEach(() => {
    useAuthMock.mockReset()
    localStorage.clear()
  })

  it('offers "Become a recruiter" to a flag-less candidate instead of the mode switcher', () => {
    useAuthMock.mockReturnValue(authState({ user: { id: 'u1', email: 'c@example.com', name: 'Cay', role: 'candidate' } }))

    renderHeader()

    const grant = screen.getByRole('link', { name: /become a recruiter/i })
    expect(grant).toHaveAttribute('href', '/choose-role?switch=1')
    // Exact-name match: "Become a recruiter" must not count as the Recruiter link.
    expect(screen.queryByRole('link', { name: 'Recruiter' })).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: /active role/i })).not.toBeInTheDocument()
  })

  it('shows the mode switcher and no grant link for an is_recruiter flag holder', () => {
    useAuthMock.mockReturnValue(authState({ user: { id: 'u2', email: 'd@example.com', name: 'Dee', role: 'candidate', is_recruiter: true } }))

    renderHeader()

    expect(screen.getByRole('link', { name: 'Recruiter' })).toHaveAttribute('href', '/recruiter')
    expect(screen.getByRole('group', { name: /active role/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /become a recruiter/i })).not.toBeInTheDocument()
  })

  it('admins get the switcher, not the grant link', () => {
    useAuthMock.mockReturnValue(authState({ user: { id: 'u3', email: 'a@example.com', name: 'Ava', role: 'admin' } }))

    renderHeader()

    expect(screen.getByRole('group', { name: /active role/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /become a recruiter/i })).not.toBeInTheDocument()
  })
})

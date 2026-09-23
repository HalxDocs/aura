import { describe, expect, it, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppHeader } from '../AppHeader'
import { useAuth } from '@/contexts/AuthContext'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

const useAuthMock = vi.mocked(useAuth)

function authState(user: Record<string, unknown>) {
  return {
    user: user as never,
    token: 'test-token',
    loading: false,
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

  it('a candidate sees candidate links and the switch-role doorway, no Recruiter link', () => {
    useAuthMock.mockReturnValue(authState({ id: 'u1', email: 'c@example.com', name: 'Cay', role: 'candidate' }))

    renderHeader()

    expect(screen.getByRole('link', { name: 'New interview' })).toHaveAttribute('href', '/interview')
    expect(screen.getByRole('link', { name: 'My interviews' })).toHaveAttribute('href', '/my-interviews')
    expect(screen.getByRole('link', { name: /switch role/i })).toHaveAttribute('href', '/choose-role?switch=1')
    // Exact-name match: "Switch role" must not count as the Recruiter link.
    expect(screen.queryByRole('link', { name: 'Recruiter' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Profile' })).toHaveAttribute('href', '/profile/candidate')
  })

  it('a recruiter sees the Recruiter link and profile, no switch-role doorway for their own side', () => {
    useAuthMock.mockReturnValue(authState({ id: 'u2', email: 'r@example.com', name: 'Rex', role: 'recruiter' }))

    renderHeader()

    expect(screen.getByRole('link', { name: 'Recruiter' })).toHaveAttribute('href', '/recruiter')
    expect(screen.getByRole('link', { name: 'Profile' })).toHaveAttribute('href', '/profile/recruiter')
    expect(screen.queryByRole('link', { name: 'New interview' })).not.toBeInTheDocument()
    // Non-admins always keep the doorway to the role picker; the server's
    // usage lock decides whether a switch actually happens.
    expect(screen.getByRole('link', { name: /switch role/i })).toBeInTheDocument()
  })

  it('an admin gets Recruiter and Admin links', () => {
    useAuthMock.mockReturnValue(authState({ id: 'u3', email: 'a@example.com', name: 'Ava', role: 'admin' }))

    renderHeader()

    expect(screen.getByRole('link', { name: 'Recruiter' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Admin' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /switch role/i })).not.toBeInTheDocument()
  })

  it('an unpicked role shows the choose-role link', () => {
    useAuthMock.mockReturnValue(authState({ id: 'u4', email: 'n@example.com', name: 'Nia', role: '' }))

    renderHeader()

    expect(screen.getByRole('link', { name: 'Choose role' })).toHaveAttribute('href', '/choose-role')
  })
})

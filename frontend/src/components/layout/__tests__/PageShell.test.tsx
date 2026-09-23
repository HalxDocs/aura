import { describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PageShell } from '../PageShell'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'c@example.com', name: 'Cay', role: 'candidate' },
    token: 't',
    loading: false,
    mode: 'candidate',
    setMode: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    setAuth: vi.fn(),
  }),
}))

describe('PageShell', () => {
  it('renders one header, the page content, and the footer', () => {
    render(
      <MemoryRouter>
        <PageShell active="dashboard">
          <div>page body</div>
        </PageShell>
      </MemoryRouter>
    )

    expect(screen.getByRole('navigation', { name: /primary/i })).toBeInTheDocument()
    expect(screen.getByText('page body')).toBeInTheDocument()
    // Exactly one footer: ReportView used to ship a second one inside pages.
    expect(screen.getAllByText(/© 2026 Aura/i)).toHaveLength(1)
  })

  it('hideLinks keeps the header to brand + account (minimal variant)', () => {
    render(
      <MemoryRouter>
        <PageShell hideLinks>
          <div>flow body</div>
        </PageShell>
      </MemoryRouter>
    )

    expect(screen.queryByRole('link', { name: /my interviews/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /aura home/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument()
  })
})

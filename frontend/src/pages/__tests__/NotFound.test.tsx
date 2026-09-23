import { describe, expect, it } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '@/contexts/AuthContext'
import { NotFound } from '../NotFound'

describe('NotFound', () => {
  it('renders the 404 message and navigation links', () => {
    // PageShell now wraps every 404 render and its AppHeader reads
    // AuthContext — the real provider (no token → anonymous) keeps the test
    // on the actual auth path instead of a mock.
    render(
      <AuthProvider>
        <MemoryRouter>
          <NotFound />
        </MemoryRouter>
      </AuthProvider>
    )

    expect(screen.getByText(/error 404/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /back to home/i })).toHaveAttribute('href', '/')
    // The header (now part of PageShell) also links "My interviews"; the
    // anonymous header renders none, so disambiguate by href count instead.
    const myInterviewsLinks = screen.getAllByRole('link', { name: /my interviews/i })
    expect(myInterviewsLinks.length).toBeGreaterThanOrEqual(1)
    expect(myInterviewsLinks[0]).toHaveAttribute('href', '/my-interviews')
    expect(screen.getByRole('link', { name: /aura home/i })).toHaveAttribute('href', '/')
  })
})

import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { Landing } from './pages/Landing'
import { InterviewFlow } from './pages/InterviewFlow'
import { AuthCallback } from './pages/AuthCallback'
import { LoginPage } from './pages/LoginPage'
import { EmailVerified } from './pages/EmailVerified'
import { ForgotPassword } from './pages/ForgotPassword'
import { ResetPassword } from './pages/ResetPassword'
import { MyInterviews } from './pages/MyInterviews'
import { AdminDashboard } from './pages/AdminDashboard'
import { SessionDetail } from './pages/SessionDetail'
import { CandidateSessionReport } from './pages/CandidateSessionReport'
import { RolePicker } from './pages/RolePicker'
import { RecruiterDashboard } from './pages/RecruiterDashboard'
import { InviteBuilder } from './pages/InviteBuilder'
import { InviteDetail } from './pages/InviteDetail'
import { InviteInterview } from './pages/InviteInterview'
import { NotFound } from './pages/NotFound'
import { CandidateProfile } from './pages/CandidateProfile'
import { RecruiterProfile } from './pages/RecruiterProfile'
import { CandidateDashboard } from './pages/CandidateDashboard'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public marketing world — anonymous-only; logged-in users are
            redirected into the app by Landing itself. */}
        <Route path="/" element={<Landing />} />

        {/* Auth world (own centered layout, no app chrome). */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/auth/verified" element={<EmailVerified />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />

        {/* Candidate flow pages: the live interview owns the whole screen
            (arena HUD), the flow steps use the minimal header. */}
        <Route path="/interview" element={<ProtectedRoute><InterviewFlow /></ProtectedRoute>} />
        {/* Standalone candidate page reached while logged out of the app. */}
        <Route path="/invite/:token" element={<InviteInterview />} />

        {/* App world — every page below renders inside its own PageShell
            (one header, one footer, one backdrop). The shell lives at the
            page, not a layout route, because each page passes its own
            `active` nav highlight. */}
        <Route path="/dashboard" element={<ProtectedRoute><CandidateDashboard /></ProtectedRoute>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/my-interviews" element={<MyInterviews />} />
          <Route path="/my-interviews/:sessionId" element={<CandidateSessionReport />} />
          <Route path="/choose-role" element={<RolePicker />} />
          <Route path="/profile/candidate" element={<CandidateProfile />} />
        </Route>
        <Route element={<ProtectedRoute requireRole="recruiter" />}>
          <Route path="/recruiter" element={<RecruiterDashboard />} />
          <Route path="/recruiter/new" element={<InviteBuilder />} />
          <Route path="/recruiter/invites/:inviteId" element={<InviteDetail />} />
          <Route path="/profile/recruiter" element={<RecruiterProfile />} />
        </Route>
        <Route element={<ProtectedRoute requireAdmin />}>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/session/:sessionId" element={<SessionDetail />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </AuthProvider>
  )
}

export default App

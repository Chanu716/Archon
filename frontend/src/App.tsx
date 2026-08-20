import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import RepositoriesPage from './pages/RepositoriesPage'
import OverviewPage from './pages/OverviewPage'
import ArchitecturePage from './pages/ArchitecturePage'
import { HealthDashboard } from './pages/HealthDashboard'
import GitDashboard from './pages/GitDashboard'
import EvolutionDashboard from './pages/EvolutionDashboard'
import IntelligenceWorkbench from './pages/IntelligenceWorkbench'

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/repositories" replace />} />
          <Route path="/repositories" element={<RepositoriesPage />} />
          <Route path="/repositories/:repoId/overview" element={<OverviewPage />} />
          <Route path="/repositories/:repoId/architecture" element={<ArchitecturePage />} />
          <Route path="/repositories/:id/health" element={<HealthDashboard />} />
          <Route path="/repositories/:repoId/git" element={<GitDashboard />} />
          <Route path="/repositories/:repoId/evolution" element={<EvolutionDashboard />} />
          <Route path="/repositories/:repoId/investigation" element={<IntelligenceWorkbench />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App

import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from '@/components/Sidebar'

export function Layout() {
  const location = useLocation()
  return (
    <div className="flex min-h-screen bg-parchment text-ink">
      <Sidebar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        {/* keyed by route → re-mounts and replays the enter animation on each navigation */}
        <div key={location.pathname} className="bs-page-transition">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

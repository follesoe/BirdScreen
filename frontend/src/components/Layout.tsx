import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from '@/components/Sidebar'
import cornerUrl from '@/assets/corner-branches.webp'

export function Layout() {
  const location = useLocation()
  return (
    <div className="flex h-screen overflow-hidden text-ink">
      <Sidebar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        {/* keyed by route → re-mounts and replays the enter animation on each navigation */}
        <div key={location.pathname} className="bs-page-transition">
          <Outlet />
        </div>
      </main>
      {/* subtle branches in the lower-right that fade into the page (decorative) */}
      <img
        src={cornerUrl}
        alt=""
        aria-hidden="true"
        className="pointer-events-none fixed right-0 bottom-0 -z-10 w-80 select-none opacity-45 sm:w-96 lg:w-[28rem]"
      />
    </div>
  )
}

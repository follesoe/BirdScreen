import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from '@/components/Sidebar'
import cornerUrl from '@/assets/corner-branches.webp'

export function Layout() {
  const location = useLocation()
  const { t } = useTranslation()
  // The mobile drawer; nav links close it via onClose, so no route-change effect needed.
  const [navOpen, setNavOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden text-ink">
      <Sidebar
        open={navOpen}
        onClose={() => {
          setNavOpen(false)
        }}
      />
      <main className="flex-1 overflow-y-auto">
        {/* mobile top bar with the menu button (hidden from md up) */}
        <div className="sticky top-0 z-20 flex items-center gap-3 border-b border-bark/20 bg-parchment-deep/95 px-4 py-3 backdrop-blur md:hidden">
          <button
            type="button"
            aria-label={t('nav.open')}
            onClick={() => {
              setNavOpen(true)
            }}
            className="rounded-lg p-1.5 text-ink hover:bg-parchment"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-6 w-6"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
            </svg>
          </button>
          <span className="font-display text-xl text-ink">{t('app.title')}</span>
        </div>
        {/* keyed by route → re-mounts and replays the enter animation on each navigation */}
        <div key={location.pathname} className="bs-page-transition px-4 py-6 sm:px-8 sm:py-7">
          <Outlet />
        </div>
      </main>
      {/* subtle branches in the lower-right that fade into the page (decorative) */}
      <img
        src={cornerUrl}
        alt=""
        aria-hidden="true"
        className="pointer-events-none fixed right-0 bottom-0 -z-10 hidden w-80 select-none opacity-45 sm:block sm:w-96 lg:w-[28rem]"
      />
    </div>
  )
}

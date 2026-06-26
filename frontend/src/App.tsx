import { HashRouter, Route, Routes } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { Gallery } from '@/pages/Gallery'
import { Logs } from '@/pages/Logs'
import { NotFound } from '@/pages/NotFound'
import { Placeholder } from '@/pages/Placeholder'

export function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Gallery />} />
          <Route path="logs" element={<Logs />} />
          <Route path="settings" element={<Placeholder titleKey="pages.settings" />} />
          <Route path="schedule" element={<Placeholder titleKey="pages.schedule" />} />
          <Route path="tvs" element={<Placeholder titleKey="pages.tvs" />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}

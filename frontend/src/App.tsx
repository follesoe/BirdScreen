import { HashRouter, Route, Routes } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { Gallery } from '@/pages/Gallery'
import { Logs } from '@/pages/Logs'
import { NotFound } from '@/pages/NotFound'
import { Schedule } from '@/pages/Schedule'
import { Settings } from '@/pages/Settings'
import { Tvs } from '@/pages/Tvs'

export function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Gallery />} />
          <Route path="logs" element={<Logs />} />
          <Route path="settings" element={<Settings />} />
          <Route path="schedule" element={<Schedule />} />
          <Route path="tvs" element={<Tvs />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}

export interface PosterInfo {
  name: string
  date: string | null
  modified: string
  size_bytes: number
}

export interface LogsResponse {
  lines: string[]
}

export interface ActiveWindow {
  start: string
  end: string
}

export interface ScheduleConfig {
  day_reset: string
  daily_cap: number
  debounce_minutes: number
  min_spacing_minutes: number
  weekday_windows: ActiveWindow[]
  weekend_windows: ActiveWindow[]
}

export interface SettingsConfig {
  model: string
  image_size: string
  upscale: boolean
  birdnet_url: string
  use_weather: boolean
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`${String(res.status)} ${res.statusText}`)
  }
  return (await res.json()) as T
}

async function putJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`${String(res.status)} ${res.statusText}`)
  }
  return (await res.json()) as T
}

export const api = {
  posters: (): Promise<PosterInfo[]> => getJson<PosterInfo[]>('/api/posters'),
  logs: (): Promise<LogsResponse> => getJson<LogsResponse>('/api/logs'),
  thumbUrl: (name: string): string => `/api/posters/${encodeURIComponent(name)}/thumb`,
  imageUrl: (name: string): string => `/api/posters/${encodeURIComponent(name)}/image`,
  schedule: (): Promise<ScheduleConfig> => getJson<ScheduleConfig>('/api/config/schedule'),
  saveSchedule: (config: ScheduleConfig): Promise<ScheduleConfig> =>
    putJson<ScheduleConfig>('/api/config/schedule', config),
  settings: (): Promise<SettingsConfig> => getJson<SettingsConfig>('/api/config/settings'),
  saveSettings: (config: SettingsConfig): Promise<SettingsConfig> =>
    putJson<SettingsConfig>('/api/config/settings', config),
}

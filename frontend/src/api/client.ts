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

export interface TvConfig {
  name: string
  ip: string
  enabled: boolean
  monitor_art_mode: boolean
}

export interface TvStatus {
  connected: boolean
  name: string | null
  model: string | null
  resolution: string | null
  firmware: string | null
  supports_art_mode: boolean
  art_mode_on: boolean | null
  paired: boolean
  token_auth: boolean
  message: string | null
}

export interface BirdnetStatus {
  connected: boolean
  status_code: number | null
  server: string | null
  message: string | null
}

export interface GenerationLogEntry {
  id: number
  created_at: string
  trigger: string
  reason: string | null
  birds: string[]
  location: string | null
  season: string | null
  weather: string | null
  model: string
  image_size: string
  output: string | null
  prompt: string | null
  total_tokens: number | null
  cost_usd: number | null
}

export interface StatusResponse {
  now: string
  bird_day_start: string
  in_active_window: boolean
  current_window: string | null
  next_window_start: string | null
  generations_today: number
  daily_cap: number
  next_state: string
  next_eligible_at: string | null
  next_reason: string
  weather: string | null
  location_name: string | null
  birdnet_connected: boolean
  species_today: string[]
  last_generation: GenerationLogEntry | null
  tvs: TvConfig[]
}

export interface GenerateResult {
  started: boolean
  message: string
}

export interface SendResult {
  ok: boolean
  message: string
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

async function postJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { method: 'POST' })
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
  tvs: (): Promise<TvConfig[]> => getJson<TvConfig[]>('/api/config/tvs'),
  saveTvs: (tvs: TvConfig[]): Promise<TvConfig[]> => putJson<TvConfig[]>('/api/config/tvs', tvs),
  tvStatus: (ip: string, pair = false): Promise<TvStatus> =>
    getJson<TvStatus>(`/api/tvs/status?ip=${encodeURIComponent(ip)}&pair=${String(pair)}`),
  birdnetStatus: (url: string): Promise<BirdnetStatus> =>
    getJson<BirdnetStatus>(`/api/birdnet/status?url=${encodeURIComponent(url)}`),
  status: (): Promise<StatusResponse> => getJson<StatusResponse>('/api/status'),
  generations: (): Promise<GenerationLogEntry[]> =>
    getJson<GenerationLogEntry[]>('/api/generations'),
  generate: (): Promise<GenerateResult> => postJson<GenerateResult>('/api/generate'),
  sendToTv: (name: string): Promise<SendResult> =>
    postJson<SendResult>(`/api/tvs/send?name=${encodeURIComponent(name)}`),
}

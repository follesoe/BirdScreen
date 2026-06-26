export interface PosterInfo {
  name: string
  date: string | null
  modified: string
  size_bytes: number
}

export interface LogsResponse {
  lines: string[]
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
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
}

export interface EngineConfig {
  browser_path: string;
  profile_dir: string;
  output_dir: string;
  humanize: Record<string, any>;
  running: boolean;
}

export interface PlatformInfo {
  name: string;
  display_name: string;
}

export interface StartParams {
  count: number;
  site: string;
  browser_type: string;
  safe_mode: boolean;
  fast: boolean;
  speed: "slow" | "normal" | "fast";
  new_chrome: boolean;
  tag: string | null;
  keyword_search: boolean;
  query: string;
  city_code: string | null;
  city_name: string | null;
  salary_min: number | null;
  salary_max: number | null;
  tag_sync: boolean;
  onboarding_completed?: boolean;
  job_type: string;
  degrees: string[];
  experience: string[];
  salary_fuzzy: boolean;
}

export interface City {
  label: string;
  value: string;
}

export interface Job {
  title?: string;
  company?: string;
  salary?: string;
  location?: string;
  address?: string;
  experience?: string;
  degree?: string;
  industry?: string;
  company_stage?: string;
  company_scale?: string;
  skills?: string[];
  welfare?: string[];
  job_labels?: string[];
  boss_name?: string;
  boss_title?: string;
  boss_active?: string;
  jd?: string;
  company_intro?: string;
  company_labels?: string[];
  collected_at?: string;
  [k: string]: any;
}

export interface ResultsResponse {
  jobs: Job[];
  file: string | null;
  files: string[];
}

async function jsonFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

/** 给 stop / pause / resume / ack / status 拼上目标任务的 task_id。 */
function taskQuery(taskId?: string): string {
  return taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
}

export const api = {
  getPlatforms: () =>
    jsonFetch<{ ok: boolean; platforms: PlatformInfo[] }>("/api/platforms"),
  getConfig: (browser = "chrome") =>
    jsonFetch<EngineConfig>(`/api/config?browser_type=${browser}`),
  start: (params: StartParams) =>
    jsonFetch<{ ok: boolean; error?: string; task_id?: string }>("/api/start", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  stop: (taskId?: string) =>
    jsonFetch<{ ok: boolean }>("/api/stop" + taskQuery(taskId), { method: "POST" }),
  pause: (taskId?: string) =>
    jsonFetch<{ ok: boolean }>("/api/pause" + taskQuery(taskId), { method: "POST" }),
  resume: (taskId?: string) =>
    jsonFetch<{ ok: boolean }>("/api/resume" + taskQuery(taskId), { method: "POST" }),
  getStatus: (taskId?: string) =>
    jsonFetch<{ running: boolean; state: string; progress: any; pending_action: any }>(
      "/api/status" + taskQuery(taskId)
    ),
  ack: (payload = "", taskId?: string) =>
    jsonFetch<{ ok: boolean }>("/api/ack" + taskQuery(taskId), {
      method: "POST",
      body: JSON.stringify({ payload }),
    }),
  getResults: (date?: string, outputDir?: string, platform?: string) => {
    const query = [
      date ? `date=${encodeURIComponent(date)}` : "",
      outputDir ? `output_dir=${encodeURIComponent(outputDir)}` : "",
      platform ? `platform=${encodeURIComponent(platform)}` : "",
    ]
      .filter(Boolean)
      .join("&");
    return jsonFetch<ResultsResponse>("/api/results" + (query ? "?" + query : ""));
  },
  getCities: () => jsonFetch<{ cities: City[] }>("/api/cities"),
  refreshCities: (browser = "chrome") =>
    jsonFetch<{ ok: boolean; error?: string; cities: City[] }>(
      `/api/cities/refresh?browser_type=${browser}`,
      { method: "POST" }
    ),
  saveConfig: (body: {
    browser_type: string;
    browser_path?: string | null;
    output_dir?: string | null;
  }) =>
    jsonFetch<{ ok: boolean; browser_path: string; output_dir: string }>(
      "/api/config",
      { method: "POST", body: JSON.stringify(body) }
    ),
  getStartParams: () =>
    jsonFetch<Partial<StartParams>>("/api/start-params"),
  saveStartParams: (params: Partial<StartParams>) =>
    jsonFetch<{ ok: boolean }>(
      "/api/start-params",
      { method: "POST", body: JSON.stringify(params) }
    ),
  resetStartParams: () =>
    jsonFetch<{ ok: boolean }>("/api/start-params/reset", { method: "POST" }),
};

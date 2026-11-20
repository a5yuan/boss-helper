import { defineStore } from "pinia";
import { watch } from "vue";
import {
  api,
  type City,
  type EngineConfig,
  type Job,
  type PlatformInfo,
  type StartParams,
} from "@/api";
import { tracer } from "@/utils/tracer";
import { useSound } from "@/composables/useSound";

/** 解析薪资文本 → [min, max]（单位 K）。无法解析返回 null。 */
function parseSalary(text?: string): [number, number] | null {
  if (!text) return null;
  const s = String(text);
  if (/\/(天|时|小时)|元\/(天|时|小时)/.test(s)) return null;
  let m = s.match(/(\d+(?:\.\d+)?)\s*[-~―]\s*(\d+(?:\.\d+)?)\s*[Kk]/);
  if (m) return [parseFloat(m[1]), parseFloat(m[2])];
  m = s.match(/(\d+(?:\.\d+)?)\s*万?\s*[-~―]\s*(\d+(?:\.\d+)?)\s*万/);
  if (m) return [parseFloat(m[1]) * 10, parseFloat(m[2]) * 10];
  m = s.match(/(\d+(?:\.\d+)?)\s*千?\s*[-~―]\s*(\d+(?:\.\d+)?)\s*千/);
  if (m) return [parseFloat(m[1]), parseFloat(m[2])];
  m = s.match(/(\d+(?:\.\d+)?)\s*[Kk]/);
  if (m) return [parseFloat(m[1]), parseFloat(m[1])];
  return null;
}

export interface LogEntry {
  id: number;
  level: string;
  msg: string;
  taskId?: string;
  platform?: string;
}

export interface PendingAction {
  reason: string;
  kind: string;
}

export type EngineState =
  | "idle"
  | "running"
  | "paused"
  | "waiting"
  | "done"
  | "stopped"
  | "error";

/** 单个任务的完整状态。界面上的「当前任务」只是其中一个。 */
export interface TaskState {
  taskId: string;
  platform: string;
  state: EngineState;
  running: boolean;
  progress: { done: number; total: number; stats: Record<string, number> };
  logs: LogEntry[];
  pendingAction: PendingAction | null;
  jobs: Job[];
  resultFiles: string[];
  currentFile: string | null;
  errorMsg: string;
  stopping: boolean;
  pausing: boolean;
  seamlessMode: boolean;
}

/** 没有对应任务时，结果先按平台寄存在这里。 */
export interface DetachedResults {
  jobs: Job[];
  resultFiles: string[];
  currentFile: string | null;
}

interface State {
  config: EngineConfig | null;
  params: StartParams;
  tasks: Record<string, TaskState>;
  taskOrder: string[];
  activeTaskId: string | null;
  platforms: PlatformInfo[];
  detachedResults: Record<string, DetachedResults>;
  cities: City[];
  citiesRefreshing: boolean;
  isFullscreen: boolean; // 新增全屏状态
  initialized: boolean;
  // WS 是全局连接，不是任务级状态；对外仍以只读 getter 暴露
  _wsConnected: boolean;
  // 没有任务承载时（例如启动校验失败）的提示
  _startError: string;
}

const EMPTY_PROGRESS = { done: 0, total: 0, stats: {} as Record<string, number> };
const TERMINAL_STATES = ["done", "stopped", "error", "idle"];

function createTaskState(taskId: string, platform: string): TaskState {
  return {
    taskId,
    platform,
    state: "idle",
    running: false,
    progress: { done: 0, total: 0, stats: {} },
    logs: [],
    pendingAction: null,
    jobs: [],
    resultFiles: [],
    currentFile: null,
    errorMsg: "",
    stopping: false,
    pausing: false,
    seamlessMode: false,
  };
}

/** 某平台最新的任务（taskOrder 末尾优先），没有返回 null。 */
function latestTaskFor(s: State, platform: string): TaskState | null {
  for (let i = s.taskOrder.length - 1; i >= 0; i--) {
    const t = s.tasks[s.taskOrder[i]];
    if (t && t.platform === platform) return t;
  }
  return null;
}

/**
 * 当前查看的任务：
 * 1. activeTaskId 指向的任务且平台与 params.site 一致；
 * 2. 否则取 taskOrder 里最后一个同平台任务；
 * 3. 都没有就是 null。
 */
function pickActiveTask(s: State): TaskState | null {
  const pinned = s.activeTaskId ? s.tasks[s.activeTaskId] : null;
  if (pinned && pinned.platform === s.params.site) return pinned;
  return latestTaskFor(s, s.params.site);
}

let logSeq = 0;
let ws: WebSocket | null = null;
const sound = useSound();

// 模块级防抖计时器（不能放在 defineStore 内部的对象字面量里）
let _saveTimer: ReturnType<typeof setTimeout> | null = null;

function _debouncedSaveParams(getParams: () => Record<string, unknown>, save: (p: Record<string, unknown>) => Promise<void>) {
  if (_saveTimer) clearTimeout(_saveTimer);
  _saveTimer = setTimeout(async () => {
    try {
      await save(getParams());
    } catch { /* 静默 */ }
  }, 800);
}

export const useEngine = defineStore("engine", {
  state: (): State => ({
    config: null,
    params: {
      count: 20,
      site: "",
      browser_type: "chrome",
      safe_mode: true,
      fast: false,
      speed: "slow",
      new_chrome: false,
      tag: null,
      keyword_search: true,
      query: "",
      city_code: null,
      city_name: null,
      salary_min: null,
      salary_max: null,
      tag_sync: true,
      onboarding_completed: false,
      job_type: "",
      degrees: [],
      experience: [],
      salary_fuzzy: false,
    },
    tasks: {},
    taskOrder: [],
    activeTaskId: null,
    platforms: [],
    detachedResults: {},
    cities: [],
    citiesRefreshing: false,
    isFullscreen: false,
    initialized: false,
    _wsConnected: false,
    _startError: "",
  }),

  getters: {
    // ── 任务选择 ──────────────────────────────────────────────────────────
    activeTask: (s): TaskState | null => pickActiveTask(s),
    multiTask: (s): boolean => s.taskOrder.length > 1,
    anyRunning: (s): boolean =>
      s.taskOrder.some((id) => !!s.tasks[id]?.running),

    // ── 兼容旧组件的只读投影（全部来自当前任务，没有时给原来的初始值） ──
    state(): EngineState {
      return this.activeTask?.state ?? "idle";
    },
    running(): boolean {
      return this.activeTask?.running ?? false;
    },
    selectedRunning(): boolean {
      return this.activeTask?.running ?? false;
    },
    progress(): { done: number; total: number; stats: Record<string, number> } {
      return this.activeTask?.progress ?? EMPTY_PROGRESS;
    },
    logs(): LogEntry[] {
      return this.activeTask?.logs ?? [];
    },
    pendingAction(): PendingAction | null {
      return this.activeTask?.pendingAction ?? null;
    },
    jobs(): Job[] {
      return (
        this.activeTask?.jobs ??
        this.detachedResults[this.params.site]?.jobs ??
        []
      );
    },
    resultFiles(): string[] {
      return (
        this.activeTask?.resultFiles ??
        this.detachedResults[this.params.site]?.resultFiles ??
        []
      );
    },
    currentFile(): string | null {
      return (
        this.activeTask?.currentFile ??
        this.detachedResults[this.params.site]?.currentFile ??
        null
      );
    },
    errorMsg(): string {
      return this._startError || this.activeTask?.errorMsg || "";
    },
    stopping(): boolean {
      return this.activeTask?.stopping ?? false;
    },
    pausing(): boolean {
      return this.activeTask?.pausing ?? false;
    },
    seamlessMode(): boolean {
      return this.activeTask?.seamlessMode ?? false;
    },
    wsConnected(): boolean {
      return this._wsConnected;
    },
    percent(): number {
      if (!this.progress.total) return 0;
      return Math.min(100, Math.round((this.progress.done / this.progress.total) * 100));
    },
    statusLabel(): string {
      return (
        {
          idle: "空闲",
          running: "运行中",
          paused: "已暂停",
          waiting: "等待操作",
          done: "已完成",
          stopped: "已停止",
          error: "出错",
        } as Record<string, string>
      )[this.state] || this.state;
    },
    canStart(): boolean {
      if (!this.config) return false;
      if (this.params.keyword_search) return !!(this.params.query || "").trim();
      return true;
    },
  },

  actions: {
    // ── 平台 / 任务选择 ──────────────────────────────────────────────────
    async loadPlatforms() {
      try {
        const r = await api.getPlatforms();
        this.platforms = r.platforms || [];
        if (!this.params.site || !this.platforms.some((p) => p.name === this.params.site)) {
          this.params.site = this.platforms[0]?.name ?? "";
        }
      } catch (e) {
        this.pushLog("error", `加载平台列表失败: ${e}`);
      }
    },

    platformLabel(platform: string): string {
      const hit = this.platforms.find((p) => p.name === platform);
      return hit?.display_name || platform;
    },

    taskFor(platform: string): TaskState | null {
      return latestTaskFor(this, platform);
    },

    /**
     * 确保 taskId 对应的任务存在。新建时如果当前平台没有任务，就顺手把视图切过去，
     * 避免刷新后标签栏显示任务、面板却停在空闲状态；当前平台已有任务则不抢焦点。
     */
    ensureTask(taskId: string, platform: string): TaskState {
      if (!this.tasks[taskId]) {
        const hadForSite = latestTaskFor(this, this.params.site);
        this.tasks[taskId] = createTaskState(taskId, platform);
        this.taskOrder.push(taskId);
        if (!hadForSite) {
          this.params.site = platform;
          this.activeTaskId = taskId;
        }
      }
      return this.tasks[taskId];
    },

    selectTask(taskId: string) {
      const task = this.tasks[taskId];
      if (!task) return;
      this.activeTaskId = taskId;
      this.params.site = task.platform;
    },

    selectPlatform(platform: string) {
      this.params.site = platform;
      const task = latestTaskFor(this, platform);
      this.activeTaskId = task ? task.taskId : null;
    },

    /** 关闭一个已结束任务；结果留在 detachedResults，视图跟着剩余任务走。 */
    closeTask(taskId: string) {
      const task = this.tasks[taskId];
      if (!task || task.running) return;

      delete this.tasks[taskId];
      this.taskOrder = this.taskOrder.filter((id) => id !== taskId);

      if (this.activeTaskId === taskId) this.activeTaskId = null;

      if (this.taskOrder.length) {
        // 当前平台已经没有任务了：把视图切到最后一个剩余任务
        if (!latestTaskFor(this, this.params.site)) {
          const lastId = this.taskOrder[this.taskOrder.length - 1];
          const last = this.tasks[lastId];
          this.activeTaskId = lastId;
          this.params.site = last.platform;
        } else if (!this.activeTaskId) {
          const siteTask = latestTaskFor(this, this.params.site);
          if (siteTask) this.activeTaskId = siteTask.taskId;
        }
      } else {
        this.activeTaskId = null;
      }

      // 关掉的任务结果不以任务形式留存，改存到平台名下
      this.detachedResults[task.platform] = {
        jobs: task.jobs,
        resultFiles: task.resultFiles,
        currentFile: task.currentFile,
      };
    },

    // ── 日志 ─────────────────────────────────────────────────────────────
    pushLog(level: string, msg: string, taskId?: string) {
      const task = taskId ? this.tasks[taskId] : this.activeTask;
      if (!task) return;
      task.logs.push({
        id: ++logSeq,
        level,
        msg,
        taskId: task.taskId,
        platform: task.platform,
      });
      if (task.logs.length > 2000) task.logs.splice(0, task.logs.length - 2000);
    },

    clearLogs(taskId?: string) {
      const task = taskId ? this.tasks[taskId] : this.activeTask;
      if (task) task.logs = [];
    },

    // ── 配置 / 参数 ──────────────────────────────────────────────────────
    async loadConfig() {
      try {
        this.config = await api.getConfig(this.params.browser_type);
        if (!this.initialized) {
          const saved = await api.getStartParams();
          if (saved && typeof saved === "object") {
            Object.assign(this.params, saved);
          }
          watch(
            () => this.params,
            () => _debouncedSaveParams(
              () => this.params as unknown as Record<string, unknown>,
              async (p) => { await api.saveStartParams(p as any); }
            ),
            { deep: true }
          );
          this.initialized = true;
        }
      } catch (e) {
        this.pushLog("error", `加载配置失败: ${e}`);
      }
    },

    async start() {
      const platform = this.params.site;
      if (this.params.keyword_search && !(this.params.query || "").trim()) {
        this._startError = "请先输入搜索关键词";
        return;
      }
      this._startError = "";
      tracer.startScope("start-collection");
      tracer.log({ layer: "FE-ACTION", fn: "engine:start", msg: "用户点击启动", scope: "start-collection", data: {
        platform,
        query: this.params.query,
        city: this.params.city_name,
        count: this.params.count,
      }});
      try {
        const r = await api.start(this.params);
        if (!r.ok || !r.task_id) {
          this._startError = r.error || "启动失败";
          this.pushLog("error", this._startError, this.taskFor(platform)?.taskId);
          tracer.log({ layer: "FE-ACTION", fn: "engine:start", msg: "启动失败", data: { error: this._startError }, scope: "start-collection" });
          tracer.endScope("start-collection");
          return;
        }

        // 新任务取代同平台上一个已结束任务，避免标签栏出现同一平台两条
        for (const id of [...this.taskOrder]) {
          if (this.tasks[id]?.platform === platform) delete this.tasks[id];
        }
        this.taskOrder = this.taskOrder.filter((id) => !!this.tasks[id]);

        const task = this.ensureTask(r.task_id, platform);
        task.state = "running";
        task.running = true;
        task.progress = { done: 0, total: this.params.count, stats: {} };
        task.seamlessMode = false;
        // 启动完成的任务就是新的查看目标
        this.params.site = platform;
        this.activeTaskId = r.task_id;
        this.connectWs();
      } catch (e) {
        this._startError = `启动失败: ${e}`;
        this.pushLog("error", this._startError, this.taskFor(platform)?.taskId);
        tracer.log({ layer: "FE-ACTION", fn: "engine:start", msg: "启动异常", data: { error: String(e) }, scope: "start-collection" });
        tracer.endScope("start-collection");
      }
    },

    async loadCities() {
      try {
        const r = await api.getCities();
        this.cities = r.cities || [];
      } catch (e) {
        this.pushLog("error", `加载城市列表失败: ${e}`);
      }
    },

    async refreshCities() {
      this.citiesRefreshing = true;
      try {
        const r = await api.refreshCities(this.params.browser_type);
        this.cities = r.cities || this.cities;
        if (!r.ok) this.pushLog("warn", r.error || "刷新城市列表失败");
        else this.pushLog("info", `城市列表已更新，共 ${this.cities.length} 个`);
      } catch (e) {
        this.pushLog("error", `刷新城市列表失败: ${e}`);
      } finally {
        this.citiesRefreshing = false;
      }
    },

    async saveConfig(patch: { browser_path?: string; output_dir?: string }) {
      try {
        const r = await api.saveConfig({
          browser_type: this.params.browser_type,
          ...patch,
        });
        if (this.config) {
          this.config.browser_path = r.browser_path;
          this.config.output_dir = r.output_dir;
        }
      } catch (e) {
        this.pushLog("error", `保存配置失败: ${e}`);
      }
    },

    async resetParams() {
      try {
        const r = await api.resetStartParams();
        if (r.ok) {
          this.initialized = false;
          await this.loadConfig();
          this.pushLog("info", "已成功重置运行配置为默认值");
        }
      } catch (e) {
        this.pushLog("error", `重置配置失败: ${e}`);
      }
    },

    // ── 任务控制（全部按 task_id 作用，缺省为当前任务） ──────────────────
    async stop(taskId?: string) {
      const task = taskId ? this.tasks[taskId] : this.activeTask;
      if (!task || task.stopping) return;
      task.stopping = true;
      this.pushLog("warn", "已发送停止指令，等待当前条目收尾 ...", task.taskId);
      tracer.startScope("stop-collection");
      tracer.log({ layer: "FE-ACTION", fn: "engine:stop", msg: "用户点击停止", scope: "stop-collection" });
      try {
        await api.stop(task.taskId);
      } catch (e) {
        this.pushLog("error", `停止失败: ${e}`, task.taskId);
        tracer.log({ layer: "FE-ACTION", fn: "engine:stop", msg: "停止失败", data: { error: String(e) }, scope: "stop-collection" });
      }
      const started = Date.now();
      const poll = async () => {
        const current = this.tasks[task.taskId];
        if (!current || !current.stopping) return;
        if (Date.now() - started > 60000) {
          this.finishStop(task.taskId);
          return;
        }
        try {
          const s = await api.getStatus(task.taskId);
          // running 是全局字段，单任务是否结束只看它自己的 state
          if (TERMINAL_STATES.includes(s.state)) {
            this.finishStop(task.taskId);
            return;
          }
        } catch {
          /* 忽略瞬时网络错误，继续轮询 */
        }
        setTimeout(poll, 800);
      };
      setTimeout(poll, 800);
    },

    async pause(taskId?: string) {
      const task = taskId ? this.tasks[taskId] : this.activeTask;
      if (!task || task.pausing || task.state !== "running") return;
      task.pausing = true;
      this.pushLog("warn", "已发送暂停指令 ...", task.taskId);
      tracer.startScope("pause-collection");
      tracer.log({ layer: "FE-ACTION", fn: "engine:pause", msg: "用户点击暂停", scope: "pause-collection" });
      try {
        await api.pause(task.taskId);
      } catch (e) {
        this.pushLog("error", `暂停失败: ${e}`, task.taskId);
        tracer.log({ layer: "FE-ACTION", fn: "engine:pause", msg: "暂停失败", data: { error: String(e) }, scope: "pause-collection" });
        task.pausing = false;
      }
    },

    async resume(taskId?: string) {
      const task = taskId ? this.tasks[taskId] : this.activeTask;
      if (!task || (!task.pausing && task.state !== "paused")) return;
      task.pausing = false;
      this.pushLog("info", "继续采集 ...", task.taskId);
      tracer.startScope("resume-collection");
      tracer.log({ layer: "FE-ACTION", fn: "engine:resume", msg: "用户点击继续", scope: "resume-collection" });
      try {
        await api.resume(task.taskId);
      } catch (e) {
        this.pushLog("error", `继续失败: ${e}`, task.taskId);
        tracer.log({ layer: "FE-ACTION", fn: "engine:resume", msg: "继续失败", data: { error: String(e) }, scope: "resume-collection" });
      }
    },

    finishStop(taskId: string) {
      const task = this.tasks[taskId];
      if (!task) return;
      task.stopping = false;
      task.pausing = false;
      task.running = false;
      task.seamlessMode = false;
      if (task.state === "running" || task.state === "waiting" || task.state === "paused") {
        task.state = "stopped";
      }
      task.pendingAction = null;
      tracer.endScope("stop-collection");
      tracer.endScope("start-collection");
      tracer.endScope("pause-collection");
      tracer.endScope("resume-collection");
      this.loadResults(task.platform);
    },

    async ack(payload = "", taskId?: string) {
      const task = taskId ? this.tasks[taskId] : this.activeTask;
      await api.ack(payload, task?.taskId);
      if (!task) return;
      task.pendingAction = null;
      if (task.running) task.state = "running";
    },

    // ── 结果 ─────────────────────────────────────────────────────────────
    async loadResults(platform?: string, date?: string) {
      const target = platform || this.params.site;
      try {
        tracer.startScope("load-results");
        tracer.log({ layer: "FE-API", fn: "engine:loadResults", msg: "加载岗位列表", scope: "load-results", data: {
          platform: target,
          date: date ?? "(latest)",
        }});
        const r = await api.getResults(date, undefined, target);
        const jobs: Job[] = (r.jobs || []).map((j: any) => {
          if (j.salary && (j.salaryMin == null || j.salaryMax == null)) {
            const parsed = parseSalary(j.salary);
            if (parsed) {
              j.salaryMin = parsed[0];
              j.salaryMax = parsed[1];
            }
          }
          return j as Job;
        });
        const task = this.taskFor(target);
        if (task) {
          task.jobs = jobs;
          task.resultFiles = r.files || [];
          task.currentFile = r.file;
        } else {
          this.detachedResults[target] = {
            jobs,
            resultFiles: r.files || [],
            currentFile: r.file,
          };
        }
        tracer.log({ layer: "FE-API", fn: "engine:loadResults", msg: "加载成功", scope: "load-results", data: {
          platform: target,
          jobs_count: jobs.length,
          current_file: r.file,
          files_count: r.files?.length,
        }});
        tracer.endScope("load-results");
      } catch (e) {
        this.pushLog("error", `加载结果失败: ${e}`, this.taskFor(target)?.taskId);
        tracer.log({ layer: "FE-API", fn: "engine:loadResults", msg: "加载失败", data: { error: String(e) }, scope: "load-results" });
        tracer.endScope("load-results");
      }
    },

    // ── WebSocket ────────────────────────────────────────────────────────
    connectWs() {
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING))
        return;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => {
        this._wsConnected = true;
        tracer.log({ layer: "FE-WS", fn: "engine:connectWs", msg: "WebSocket 已连接", scope: this.anyRunning ? "start-collection" : undefined });
      };
      ws.onclose = () => {
        this._wsConnected = false;
        // 只要还有任一任务在跑（或后端报告有任务）就重连，不能只看当前任务
        if (this.anyRunning || this.config?.running) setTimeout(() => this.connectWs(), 1000);
      };
      ws.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        tracer.log({ layer: "FE-WS", fn: "engine:handleEvent", msg: `收到 WS 消息: ${data.type}`, data, scope: this.anyRunning ? "start-collection" : undefined });
        this.handleEvent(data);
      };
    },

    /** 事件按 task_id 路由，绝不写进「当前任务」。 */
    handleEvent(ev: any) {
      const taskId: string = ev.task_id || this.activeTaskId || "";
      if (!taskId) return;
      const task = this.tasks[taskId]
        ?? this.ensureTask(taskId, ev.platform || this.params.site);

      switch (ev.type) {
        case "log":
          this.pushLog(ev.level || "info", ev.msg ?? "", task.taskId);
          if (ev.level === "error") {
            tracer.log({ layer: "FE-ACTION", fn: "engine:handleEvent", msg: "引擎日志错误", data: { msg: ev.msg }, scope: this.anyRunning ? "start-collection" : undefined });
          }
          break;
        case "progress":
          task.progress = {
            done: ev.done ?? 0,
            total: ev.total ?? task.progress.total,
            stats: ev.stats ?? {},
          };
          break;
        case "status":
          task.state = ev.state as EngineState;
          tracer.log({ layer: "FE-ACTION", fn: "engine:handleEvent", msg: `状态变更: ${ev.state}`, data: { detail: ev.detail }, scope: this.anyRunning ? "start-collection" : undefined });
          if (ev.state === "running" || ev.state === "paused" || ev.state === "waiting") {
            task.running = true;
          }
          if (ev.state === "done" || ev.state === "stopped") {
            task.running = false;
            task.stopping = false;
            task.pausing = false;
            task.seamlessMode = false;
            this.loadResults(task.platform);
            if (ev.state === "done") {
              sound.play("done");
              try { (window as any).pywebview?.api?.flash_taskbar?.(3); } catch { /* 静默 */ }
            }
          }
          if (ev.state === "error") {
            const wasStopping = task.stopping;
            task.running = false;
            task.stopping = false;
            task.pausing = false;
            task.seamlessMode = false;
            if (wasStopping || String(ev.detail ?? "").includes("被停止")) {
              task.state = "stopped";
            }
            task.errorMsg = String(ev.detail ?? "");
            this.loadResults(task.platform);
            sound.play("error");
            try { (window as any).pywebview?.api?.flash_taskbar?.(8); } catch { /* 静默 */ }
          }
          if (ev.state === "paused") {
            task.pausing = false;
          }
          break;
        case "need_action":
          task.pendingAction = { reason: ev.reason, kind: ev.kind || "confirm" };
          task.state = "waiting";
          sound.play("alert");
          try { (window as any).pywebview?.api?.flash_taskbar?.(6); } catch { /* 静默 */ }
          tracer.log({ layer: "FE-ACTION", fn: "engine:handleEvent", msg: "需要用户操作", data: { reason: ev.reason, kind: ev.kind }, scope: this.anyRunning ? "start-collection" : undefined });
          break;
        case "seamless_mode":
          task.seamlessMode = ev.enabled;
          break;
      }
    },
  },
});

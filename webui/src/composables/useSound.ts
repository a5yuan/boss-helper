/**
 * useSound — Web Audio API 提示音，无需音频文件。
 * 适合：采集完成、需要操作、错误等场景。
 *
 * 如需替换为真实音频文件，只需把 generateTone 换成 new Audio(url).play()
 * 或 new Audio("data:audio/wav;base64,...").play()
 */
import { useLocalStorage } from "./useLocalStorage";

export type SoundKind = "alert" | "done" | "error";

const _ctx: { ctx: AudioContext | null } = { ctx: null };

function ctx(): AudioContext {
  if (!_ctx.ctx || _ctx.ctx.state === "closed") {
    _ctx.ctx = new AudioContext();
  }
  return _ctx.ctx;
}

/** 合成一段短促音频（各音色区分度足够） */
function generateTone(kind: SoundKind): void {
  try {
    const ac = ctx();
    const now = ac.currentTime;

    const master = ac.createGain();
    master.connect(ac.destination);
    master.gain.setValueAtTime(0.35, now);

    if (kind === "alert") {
      // 两声短促蜂鸣（提示用户需要操作）
      for (let i = 0; i < 2; i++) {
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.connect(g);
        g.connect(master);
        osc.type = "sine";
        osc.frequency.setValueAtTime(880, now + i * 0.35);
        g.gain.setValueAtTime(0, now + i * 0.35);
        g.gain.linearRampToValueAtTime(1, now + i * 0.35 + 0.02);
        g.gain.exponentialRampToValueAtTime(0.001, now + i * 0.35 + 0.25);
        osc.start(now + i * 0.35);
        osc.stop(now + i * 0.35 + 0.25);
      }
    } else if (kind === "done") {
      // 上升三音（任务完成）
      const notes = [523, 659, 784];
      notes.forEach((freq, i) => {
        const osc = ac.createOscillator();
        const g = ac.createGain();
        osc.connect(g);
        g.connect(master);
        osc.type = "sine";
        osc.frequency.setValueAtTime(freq, now + i * 0.18);
        g.gain.setValueAtTime(0, now + i * 0.18);
        g.gain.linearRampToValueAtTime(1, now + i * 0.18 + 0.02);
        g.gain.exponentialRampToValueAtTime(0.001, now + i * 0.18 + 0.3);
        osc.start(now + i * 0.18);
        osc.stop(now + i * 0.18 + 0.3);
      });
    } else {
      // error：一声低长音
      const osc = ac.createOscillator();
      const g = ac.createGain();
      osc.connect(g);
      g.connect(master);
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(220, now);
      osc.frequency.linearRampToValueAtTime(180, now + 0.6);
      g.gain.setValueAtTime(0, now);
      g.gain.linearRampToValueAtTime(1, now + 0.03);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.6);
      osc.start(now);
      osc.stop(now + 0.6);
    }
  } catch {
    // 音频上下文不可用时静默跳过
  }
}

export function useSound() {
  /** 用户可随时开关，状态持久化 */
  const enabled = useLocalStorage("boss-sound-enabled", true);

  function play(kind: SoundKind = "alert") {
    if (!enabled.value) return;
    generateTone(kind);
  }

  return { enabled, play };
}

/** 全局回调，供 pywebview API 调用 */
if (typeof window !== "undefined") {
  (window as any).__playSound = (kind: string) => {
    if (["alert", "done", "error"].includes(kind)) {
      generateTone(kind as SoundKind);
    }
  };
}

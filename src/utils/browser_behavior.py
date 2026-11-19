import time
import random


VALID_SPEEDS = ("slow", "normal", "fast")

# 速度档位：bands 为 (累计概率, 下限秒, 上限秒)，按顺序命中；最后一段兜底。
# slow 保持原安全模式节奏，normal / fast 只调整本地等待，不改变读取方式。
SPEED_PROFILES = {
    "slow": {
        "label": "慢速",
        "bands": ((0.35, 1.2, 2.8), (0.85, 3.2, 6.0), (1.0, 8.0, 15.0)),
        "step_break_every": 12,
        "step_break_range": (8.0, 18.0),
        "scroll_detail": True,
        "scroll_wait_ms": 600,
        "click_delay_ms": 300,
        "click_settle_s": 0.5,
    },
    "normal": {
        "label": "中速",
        "bands": ((0.50, 0.8, 1.8), (1.0, 2.0, 4.0)),
        "step_break_every": 25,
        "step_break_range": (4.0, 8.0),
        "scroll_detail": True,
        "scroll_wait_ms": 450,
        "click_delay_ms": 200,
        "click_settle_s": 0.3,
    },
    "fast": {
        "label": "快速",
        "bands": ((1.0, 0.3, 0.8),),
        "step_break_every": 0,
        "step_break_range": (0.0, 0.0),
        "scroll_detail": False,
        "scroll_wait_ms": 250,
        "click_delay_ms": 100,
        "click_settle_s": 0.1,
    },
}

DEFAULT_SPEED = "slow"


def resolve_speed(speed=None, safe_mode=True, fast=False):
    """把 speed / safe_mode / fast 归一成一个档位。

    speed 显式传入时优先；否则兼容旧参数：fast 或关闭 safe_mode 视为 fast。
    """
    if speed in VALID_SPEEDS:
        return speed
    if fast or not safe_mode:
        return "fast"
    return DEFAULT_SPEED


class BrowserBehavior:
    """浏览器交互行为封装：点击卡片、滚动、间隔延迟。"""

    def __init__(self, speed=None, safe_mode=True, fast=False):
        self.speed = resolve_speed(speed, safe_mode, fast)
        self.profile = SPEED_PROFILES[self.speed]

    def get_browse_delay(self):
        dice = random.random()
        for threshold, lo, hi in self.profile["bands"]:
            if dice < threshold:
                return random.uniform(lo, hi)
        threshold, lo, hi = self.profile["bands"][-1]
        return random.uniform(lo, hi)

    def should_scroll_detail(self):
        return bool(self.profile["scroll_detail"])

    def maybe_step_break(self, success_count, sleep_fn=None):
        """按档位在每 N 条后休息；返回是否真的休息了。"""
        every = self.profile["step_break_every"]
        if not every or success_count <= 0 or success_count % every:
            return False
        idle = random.uniform(*self.profile["step_break_range"])
        print(f"\n  [IDLE] 间隔休息 {idle:.1f}s ...")
        if sleep_fn:
            sleep_fn(idle)
        else:
            time.sleep(idle)
        return True


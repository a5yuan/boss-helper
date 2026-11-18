"""硬约束：不允许绕过 src/utils/chat_input.fill_chat_input 直接改聊天框 DOM。

背景：直接 `innerText = ...` 只改 DOM，不触发框架输入处理，BOSS 的草稿存不下来；
而且填完不失焦就导航，草稿同样会丢。见 LESSONS.md。

这条测试扫描源码，发现违规写法直接失败，防止再犯。
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCAN_DIRS = ("src", "server")
SKIP_DIRS = {"__pycache__", "node_modules", "static", ".venv"}

# 写入型赋值（读操作如 `n.innerText || ''` 不算）
BANNED = (
    re.compile(r"\.innerText\s*=(?!=)"),
    re.compile(r"\.value\s*=(?!=)"),
    re.compile(r"setter\.call\("),
)

# 唯一允许写 DOM 文本的地方
ALLOW_FILE = os.path.join("src", "utils", "chat_input.py")


def _iter_files():
    for base in SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, base)):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if fn.endswith((".py", ".js")):
                    yield os.path.relpath(os.path.join(dirpath, fn), ROOT)


class TestChatInputPolicy(unittest.TestCase):
    def test_no_direct_dom_text_write(self):
        offenders = []
        for rel in _iter_files():
            path = os.path.join(ROOT, rel)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    if line.strip().startswith("#") or line.strip().startswith("//"):
                        continue
                    for pat in BANNED:
                        if pat.search(line):
                            offenders.append(f"{rel}:{lineno}  {line.strip()[:70]}")
        self.assertEqual(
            offenders, [],
            "发现绕过 chat_input 的写法，请改用 src/utils/chat_input.fill_chat_input：\n"
            + "\n".join(offenders),
        )

    def test_chat_input_uses_real_insert(self):
        path = os.path.join(ROOT, "src", "utils", "chat_input.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("Input.insertText", src, "写输入必须走 CDP Input.insertText")
        self.assertIn("def blur(", src, "必须提供失焦，否则草稿不会保存")

    def test_fill_path_blurs_before_leaving(self):
        """填完之后必须失焦，否则草稿丢失。"""
        path = os.path.join(ROOT, "src", "utils", "chat_input.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("blur_after", src)
        self.assertIn("blur(chrome)", src)


if __name__ == "__main__":
    unittest.main()

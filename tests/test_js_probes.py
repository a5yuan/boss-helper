"""真执行 JS 探针：用 node --test 跑 tests/js/，把退出码转成 unittest 结果。

Python 侧的 FakePage 只匹配 marker 字符串，探针本身零覆盖；这层用
node:vm + DOM shim 真的执行 src/js/*.js，锁住页面结构假设与回退分支。
机器上没有 node 时 skip，不把缺工具当成失败。
"""
import glob
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_TEST_DIR = os.path.join(ROOT, "tests", "js")
PROBE_DIR = os.path.join(ROOT, "src", "js")
NODE = shutil.which("node")


def _test_files() -> list[str]:
    return sorted(glob.glob(os.path.join(JS_TEST_DIR, "*.test.mjs")))


@unittest.skipUnless(NODE, "没有找到 node，跳过 JS 探针测试")
class TestJsProbes(unittest.TestCase):
    def test_all_probe_tests_pass(self):
        files = _test_files()
        self.assertTrue(files, "tests/js 下没有任何 *.test.mjs")
        proc = subprocess.run(
            [NODE, "--test", *files],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        self.assertEqual(proc.returncode, 0, output)
        # TAP 与 spec 两种报告器的汇总行都认，确保不是 0 个用例空跑
        match = re.search(r"^\s*(?:#|ℹ)\s*pass\s+(\d+)\s*$", output, re.MULTILINE)
        self.assertIsNotNone(match, f"没找到 node --test 的 pass 汇总行:\n{output}")
        passed = int(match.group(1))
        self.assertGreaterEqual(passed, 10, f"JS 用例数异常: {passed}\n{output}")
        print(f"\n[node --test] {passed} 个 JS 用例通过")

    def test_every_zhaopin_probe_has_a_test_file(self):
        """新增智联探针必须同时加测试，避免又出现零覆盖的页面假设。"""
        probes = sorted(
            os.path.basename(p)
            for p in glob.glob(os.path.join(PROBE_DIR, "zhaopin_*.js"))
        )
        self.assertTrue(probes, "src/js 下没有智联探针")
        missing = [p for p in probes
                   if not os.path.exists(os.path.join(JS_TEST_DIR, p[:-3] + ".test.mjs"))]
        self.assertEqual(missing, [], f"这些探针没有 JS 测试: {missing}")


if __name__ == "__main__":
    unittest.main()

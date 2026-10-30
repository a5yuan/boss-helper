"""一键打包脚本：前端 build + PyInstaller exe。
用法：python build_exe.py

输出目录：dist/BOSS直聘助手/
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
WEBUI = ROOT / "webui"
DIST = ROOT / "dist"
SPEC = ROOT / "boss.spec"


def run(cmd: list[str], cwd: Path | None = None, desc: str = ""):
    print(f"\n{'='*60}\n>>> {desc or ' '.join(cmd)}\n{'='*60}")
    # Windows 上 subprocess 不会自动解析 .cmd/.bat，用 shell=True
    r = subprocess.run(" ".join(cmd), cwd=str(cwd) if cwd else None, shell=True)
    if r.returncode != 0:
        print(f"[FAIL] 命令失败: {' '.join(cmd)}")
        sys.exit(r.returncode)
    print(f"[OK] {desc or cmd[0]}")


def main():
    os.chdir(ROOT)

    # 1. 前端构建
    print("\n[Step 1/3] 前端构建 (npm run build)...")
    run(["npm", "run", "build"], cwd=WEBUI, desc="前端构建")

    # 2. 清理旧产物
    for d in [DIST, ROOT / "build"]:
        if d.exists():
            print(f"[Clean] 删除旧产物: {d}")
            shutil.rmtree(d)

    # 3. PyInstaller 打包（使用 venv 中的 python，确保用对版本）
    pyinstaller = ROOT / ".venv" / "Scripts" / "python.exe"
    print("\n[Step 3/3] PyInstaller 打包...")
    run(
        [str(pyinstaller), "-m", "PyInstaller", str(SPEC), "--clean", "-y"],
        cwd=ROOT,
        desc="PyInstaller 打包",
    )

    # 完成
    final = DIST / "BOSS直聘助手"
    if final.exists():
        # 4. 拷贝使用说明.txt
        txt_guide = ROOT / "使用说明.txt"
        if txt_guide.exists():
            print("\n[Step 4/4] 正在拷贝使用说明到发布目录...")
            shutil.copy2(txt_guide, final / "使用说明.txt")
            print("[OK] 拷贝使用说明.txt 完成")

        size = sum(f.stat().st_size for f in final.rglob("*") if f.is_file())
        size_mb = size / 1024 / 1024
        print(f"\n{'='*60}")
        print(f"[SUCCESS] 打包完成！")
        print(f"输出目录: {final}")
        print(f"文件大小: ~{size_mb:.1f} MB")
        print(f"主程序:   {final / 'BOSS直聘助手.exe'}")
        print(f"说明文档: {final / '使用说明.txt'}")
        print(f"{'='*60}\n")
    else:
        print("[WARN] 打包完成，但未找到预期输出目录。请检查 PyInstaller 输出。")


if __name__ == "__main__":
    main()

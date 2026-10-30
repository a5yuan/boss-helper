# BOSS 助手 - 环境初始化脚本（并行版）
# 用法：.\init_env.ps                    # 默认使用清华镜像
#       .\init_env.ps -NoMirror           # 不使用镜像
# =========================================================

param(
    [switch]$NoMirror
)

$ErrorActionPreference = "Continue"
$PROJECT_ROOT = $PSScriptRoot
if (-not $PROJECT_ROOT) { $PROJECT_ROOT = $scriptPath }

# pip 参数（分开定义避免空格问题）
if ($NoMirror) {
    $PIP_ARGS = @()
} else {
    $PIP_ARGS = @("-i", "https://pypi.tuna.tsinghua.edu.cn/simple")
}

function Write-Step { param($msg) Write-Host "[*] $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "[+] $msg" -ForegroundColor Green }
function Write-Skip { param($msg) Write-Host "[=] $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "[-] $msg" -ForegroundColor Red }
function Write-Job  { param($msg) Write-Host "    $msg" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "========================================" -ForegroundColor Gray
Write-Host " BOSS 助手 - 环境初始化（并行）" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Gray
Write-Host ""

# =========================================================
# 参数摘要
# =========================================================
Write-Step ("Python 镜像: " + $(if ($NoMirror) { "官方 PyPI" } else { "清华镜像（默认）" }))

# =========================================================
# 前置检查
# =========================================================
$VENV    = Join-Path $PROJECT_ROOT ".venv"
$WEBUI   = Join-Path $PROJECT_ROOT "webui"
$VENV_OK = (Test-Path $VENV)
$WEBUI_OK = (Test-Path $WEBUI)
$NM_OK   = $false
if ($WEBUI_OK) { $NM_OK = (Test-Path (Join-Path $WEBUI "node_modules")) }

# Python 线：venv 已存在 + requirements 不存在 → 整个 Python 线跳过
$REQS    = Join-Path $PROJECT_ROOT "requirements.txt"
$REQS_OK = (Test-Path $REQS)

$PY_SKIP = $VENV_OK -and (-not $REQS_OK)
$NM_SKIP = $NM_OK

if ($PY_SKIP -and $NM_SKIP) {
    Write-Skip "Python 环境已就绪"
    Write-Skip "Node.js 依赖已就绪"
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Gray
    Write-Host " 环境就绪，可以运行：" -ForegroundColor White
    Write-Host ""
    Write-Host "  开发模式: python run_gui.py --dev" -ForegroundColor Cyan
    Write-Host "  生产模式: python run_gui.py" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Gray
    exit 0
}

# =========================================================
# Step 1: 启动 npm install 后台任务（并行线）
# =========================================================
$npmJob = $null
if ($WEBUI_OK -and -not $NM_OK) {
    Write-Step "启动 npm install（后台）..."
    $npmJob = Start-Job -ScriptBlock {
        param($dir, $useMirror)
        Set-Location $dir
        $out = @()
        if ($useMirror) {
            $out += npm install --registry https://registry.npmmirror.com 2>&1
        } else {
            $out += npm install 2>&1
        }
        @{
            ExitCode = $LASTEXITCODE
            Output   = $out
        }
    } -ArgumentList $WEBUI, $(-not $NoMirror)
    Write-Job "npm install 运行中..."
} else {
    Write-Step "跳过 npm install（已存在或 webui 不存在）"
}

# =========================================================
# Step 2: Python 线（主线程，venv → pip → requirements）
# =========================================================
$PY_RESULT = "skipped"
if (-not $PY_SKIP) {
    if (-not $VENV_OK) {
        Write-Step "设置 Python 版本..."
        pyenv local 3.12.0
        if ($LASTEXITCODE -ne 0) { Write-Fail "pyenv local 失败"; exit 1 }
        Write-Step "创建 .venv..."
        python -m venv $VENV
        if ($LASTEXITCODE -ne 0) { Write-Fail "venv 创建失败"; exit 1 }
        Write-OK ".venv 创建完成"
    } else {
        Write-Step ".venv 已存在，跳过创建"
    }

    Write-Step "升级 pip..."
    $VENV_PY = Join-Path $VENV "Scripts\python.exe"
    & $VENV_PY -m pip install --upgrade pip --quiet @PIP_ARGS
    Write-OK "pip 升级完成"

    if ($REQS_OK) {
        Write-Step "安装 Python 依赖..."
        & $VENV_PY -m pip install -r $REQS --quiet @PIP_ARGS
        if ($LASTEXITCODE -ne 0) { Write-Fail "requirements.txt 安装失败"; exit 1 }
        Write-OK "Python 依赖安装完成"
    } else {
        Write-Skip "requirements.txt 未找到，跳过"
    }
    $PY_RESULT = "done"
}

# =========================================================
# Step 3: 等待 npm 任务完成
# =========================================================
if ($npmJob) {
    Write-Step "等待 npm install 完成..."
    $npmResult = Wait-Job $npmJob | Receive-Job -Keep
    Remove-Job $npmJob -Force
    Write-Host ""

    if ($npmResult.ExitCode -eq 0) {
        Write-OK "Node.js 依赖安装完成"
    } else {
        Write-Fail "npm install 失败（退出码: $($npmResult.ExitCode)）"
        $npmResult.Output | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    }
}

# =========================================================
# Step 4: 摘要
# =========================================================
Write-Host ""
Write-Host "========================================" -ForegroundColor Gray
Write-Host " 环境就绪，可以运行：" -ForegroundColor White
Write-Host ""
Write-Host "  开发模式: python run_gui.py --dev" -ForegroundColor Cyan
Write-Host "  生产模式: python run_gui.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "========================================" -ForegroundColor Gray
Write-Host ""

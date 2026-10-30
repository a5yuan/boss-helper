# BOSS-Helper

[English](README_EN.md) | 简体中文

> 一个专为 zhipin.com 设计的**浏览器辅助工具**。
> 直接从你浏览器**当前渲染的页面**中读取岗位信息。
> **对 zhipin.com 发送 0 个主动 HTTP 请求。**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 核心亮点

BOSS-Helper 是一个轻量级工具，支持 **桌面可视化窗口 (pywebview)** 与 **命令行 (CLI)** 两种模式。

它通过 Chrome DevTools Protocol (CDP) 连接到你现有的 Chrome/Edge 浏览器，并读取页面上已经渲染好的岗位数据卡片——**整个过程不会向服务器发送任何直接请求**。

**与传统工具的本质区别：** 
传统工具通常通过自动化接口请求来批量获取数据；而本工具是基于你真实的物理浏览（你手动搜索、登录），工具只负责通过本地内存阅读你正在浏览的页面。一切由你主导，工具只是你的助手。

---

## 设计原则

| 原则 | 含义说明 |
|---|---|
| **0 目标请求** | 仅读取本地已经渲染完成的页面状态 |
| **复用用户鉴权** | 依托真实的浏览器会话，需要用户在自己的浏览器中正常登录 |
| **人类主导** | 由用户手动执行关键的搜索和导航，工具仅负责繁琐的提取与读取 |
| **原生内核保护** | 保持浏览器的纯净状态，不进行任何侵入式的底层注入 |
| **纯粹的技术探索** | 专注于协议与自动化的学习研究，保持极简架构，绝无冗余 |

---

## 快速开始

### 桌面 GUI 模式

```powershell
# 1. 克隆代码仓库
git clone https://github.com/qinquan-ai/boss_helper.git
cd boss-helper

# 2. 安装基础依赖
pip install -r requirements.txt

# 3. 安装 GUI 界面依赖
pip install "boss-helper[gui]"

# 4. 启动可视化程序
python run_gui.py
```

### 纯命令行 CLI 模式

```powershell
python main.py --new -b chrome -n 20
```

---

## 工作原理

```text
┌─────────────────────────────────────────────────────┐
│  你的真实浏览器 (Chrome / Edge)                        │
│  ┌─────────────────────────────────────────────┐   │
│  │  https://www.zhipin.com/web/geek/jobs       │   │
│  │  (你已登录。你搜索了岗位。你在看页面)           │   │
│  └─────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────┘
                   │  Chrome DevTools Protocol (CDP)
                   │  ← 本地 WebSocket 通信
┌──────────────────▼──────────────────────────────────┐
│  BOSS-Helper (CLI 或 pywebview)                     │
│   • VueExtractor    → 从 DOM 组件树读取卡片 ID      │
│   • DetailPanelReader → 从 Vue 实例内存读取详情内容 │
│   • OutputWriter    → 导出数据到 jobs_*.json        │
└─────────────────────────────────────────────────────┘
```

**所有数据交换均发生在本地 WebSocket 通道上。**

---

## 目录结构

```
boss-helper/
├── main.py                  # CLI 命令行入口
├── run_gui.py               # 桌面 GUI 启动器
├── server/                  # FastAPI 本地后端服务
│   ├── app.py
│   ├── session.py
│   └── tracer.py
├── webui/                   # Vue 3 + Vite 现代前端界面
├── src/
│   ├── collector.py         # 核心分析轮询调度
│   ├── config.py            # 配置加载
│   ├── core/
│   │   ├── browser.py       # CDP 浏览器控制类
│   │   └── extractor.py     # DOM & Vue 内存提取器
│   └── utils/               # 工具类 (点击辅助等)
├── docs/                    # 文档目录
├── CHANGELOG.md             # 更新日志
├── LEGAL.md                 # 法律合规与免责声明
└── LICENSE                  # 开源协议
```

---

## 已知局限性

1. **薪资乱码问题**：由于平台使用了特殊的 CSS 字体渲染技术，读取到的薪资文本可能偶尔乱码，请以浏览器中人眼看到的真实数据为准。
2. **必须先登录**：启动前请在浏览器中保持登录状态。
3. **频率限制**：使用工具辅助浏览仍可能触发平台的前端频率限制，请控制使用节奏，后果自负。

---

## 法律合规声明 (Compliance)

**极其重要：使用本软件前请务必阅读 [LEGAL.md](LEGAL.md) 的完整法律免责声明。**

简而言之：本工具通过 CDP 读取浏览器中已显示的数据。用户需自行确保使用场景符合平台用户协议及当地法律法规。

---

## 贡献指南

欢迎提交 PR 和 Issue！参与贡献前请阅读我们的 [Code of Conduct](CODE_OF_CONDUCT.md)。

---

## 开源协议

本项目采用 MIT 协议。详见 [LICENSE](LICENSE) 文件。

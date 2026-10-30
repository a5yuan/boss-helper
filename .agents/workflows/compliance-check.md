# Compliance Check

## Description
Scan the workspace for any sensitive terms (e.g., 爬虫, 反爬, 防封, 抓取, 绕过) and ensure compliant terminology is used instead.

## Steps
1. **Source Code Audit**: Search the entire workspace (excluding node_modules, .venv, dist, build, profiles) for any occurrences of sensitive keywords like "爬虫", "反爬", "防封", "封号", "绕过登录", "绕过安全", "数据抓取".
2. **Analysis**: Check if any found terms are used in comments, documentation, UI labels, or code strings. Ensure that compliant terms (e.g., "助手/整理/分析/免 WebDriver 模式/调试通道") are used instead.
3. **Report Results**: If any sensitive terms are found, list the file paths and line numbers, and suggest compliance rewrites. If none are found, report that the codebase is 100% compliant.

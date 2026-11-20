/* zhaopin:scroll — 把窗口和指定面板滚到底。
   实测智联搜索页只 SSR 首屏 20 条，滚动不会触发加载更多；这里只为
   保持引擎的滚动节奏与复核页定位一致。 */
(() => {
  try {
    if (__SCROLL_WINDOW__) window.scrollTo(0, document.body.scrollHeight);
    const panel = document.querySelector('__SELECTOR__');
    if (panel) panel.scrollTop = panel.scrollHeight;
    return JSON.stringify({ ok: true });
  } catch (e) {
    return JSON.stringify({ ok: false, reason: String(e) });
  }
})()

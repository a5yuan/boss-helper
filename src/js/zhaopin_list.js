/* zhaopin:list — 读取搜索页 SSR 初始状态里的岗位列表。
   智联搜索页未登录也会渲染 20 条，数据在 window.__INITIAL_STATE__.positionList。
   列表 DOM 的薪资是脱敏的 `**-**元`，真实薪资只在 state 里，所以这里只读 state。 */
(() => {
  try {
    const state = window.__INITIAL_STATE__ || {};
    const list = Array.isArray(state.positionList) ? state.positionList : [];
    return JSON.stringify(list);
  } catch (e) {
    return JSON.stringify({ __error__: String(e) });
  }
})()

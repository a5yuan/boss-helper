/* zhaopin:login — 页面可读性探针。

   智联游客态也能读全量列表和完整 JD，所以这里的 `in` 表示「页面可读」，
   不等于「账号已登录」。只有真的落在登录入口页（passport / /login）才报
   `login`，避免引擎把可读的游客首页误判成需要扫码。 */
(() => {
  try {
    const url = location.href || '';
    if (!url.includes('zhaopin.com')) {
      return JSON.stringify({ state: 'unknown', source: 'not_zhaopin' });
    }

    const state = window.__INITIAL_STATE__ || {};
    const user = state.user;
    if (user && typeof user === 'object' && Object.keys(user).length > 0) {
      return JSON.stringify({ state: 'in', source: 'state_user' });
    }

    if (url.includes('passport') || url.includes('/login')) {
      return JSON.stringify({ state: 'login', source: 'login_url' });
    }

    return JSON.stringify({ state: 'in', source: 'guest_session' });
  } catch (e) {
    return JSON.stringify({ state: 'unknown', source: 'error' });
  }
})()

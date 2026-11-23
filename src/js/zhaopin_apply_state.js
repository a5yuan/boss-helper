/* zhaopin:apply-state — 读投递前的状态，不做任何点击。
   数据来源：
   - positionList[i]：alreadyApply / hasAppliedPosition / applyType 判断是否已投；
   - selectedJobId：右侧详情面板当前展示的是哪条岗位，必须与目标一致才能点；
   - state.user：游客页为 []，非空才算登录（投递需要登录态）。
   按钮实测选择器：button.job-detail-summary__apply（文案「立即投递」），
   只在详情面板选中目标岗位后才返回。 */
(() => {
  try {
    const state = window.__INITIAL_STATE__ || {};
    const list = Array.isArray(state.positionList) ? state.positionList : [];
    const id = __JOB_ID__;
    let index = list.findIndex(x => x && String(x.number) === id);
    if (index < 0) index = list.findIndex(x => x && String(x.jobId) === id);
    if (index < 0) return JSON.stringify({ ok: true, found: false, reason: 'job_not_in_list' });

    const item = list[index];
    const user = state.user;
    const loggedIn = Array.isArray(user)
      ? user.length > 0
      : !!(user && typeof user === 'object' && Object.keys(user).length);
    const selected = String(state.selectedJobId || '') === String(item.number || '')
      || String(state.selectedJobId || '') === String(item.jobId || '');

    let button = { found: false };
    if (selected) {
      const btns = Array.from(document.querySelectorAll('button.job-detail-summary__apply'));
      const el = btns.find(b => /投递/.test(b.innerText || ''));
      if (el) {
        const r = el.getBoundingClientRect();
        button = {
          found: true,
          text: (el.innerText || '').trim(),
          disabled: !!el.disabled,
          x: Math.round(r.left + r.width / 2),
          y: Math.round(r.top + r.height / 2),
          w: Math.round(r.width),
          h: Math.round(r.height),
        };
      }
    }

    return JSON.stringify({
      ok: true,
      found: true,
      index: index,
      number: String(item.number || ''),
      company: item.companyName || '',
      title: item.name || '',
      logged_in: loggedIn,
      selected: selected,
      already_apply: item.alreadyApply === true,
      has_applied_position: item.hasAppliedPosition === true,
      apply_type: item.applyType === undefined ? null : item.applyType,
      button: button,
    });
  } catch (e) {
    return JSON.stringify({ ok: false, reason: 'state_error: ' + String(e) });
  }
})()

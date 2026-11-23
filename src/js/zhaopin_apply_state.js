/* zhaopin:apply-state — 读投递前的状态，不做任何点击。
   数据来源：
   - positionList[i]：alreadyApply / hasAppliedPosition / applyType 判断是否已投；
   - 详情面板 DOM：标题与公司跟目标岗位比对，对得上才算选中（主判据）；
   - selectedJobId：SSR 快照，hydrate 后不再更新，只在 DOM 读不到时兜底；
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
    // selectedJobId 是 SSR 首屏快照，hydrate 之后点卡片不会回写它（实测：
    // 点完卡片详情标题变了，这个字段纹丝不动）。所以先看 DOM，再看快照。
    const norm = s => String(s == null ? '' : s).replace(/\s+/g, '').trim();
    const titleEl = document.querySelector('.job-detail-summary__title-text');
    const panelEl = document.querySelector('.job-detail-panel')
      || document.querySelector('.job-detail-summary');
    const domTitle = norm(titleEl && titleEl.innerText);
    const panelText = norm(panelEl && panelEl.innerText);
    const domSelected = !!domTitle
      && domTitle === norm(item.name)
      && (!item.companyName || panelText.indexOf(norm(item.companyName)) >= 0);
    const snapshotSelected = String(state.selectedJobId || '') === String(item.number || '')
      || String(state.selectedJobId || '') === String(item.jobId || '');
    const selected = domSelected || snapshotSelected;

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

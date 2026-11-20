/* zhaopin:item — 按岗位 id 在 __INITIAL_STATE__.positionList 里定位详情。
   智联点卡片不会更新 state.jobDetail（选中态不变），详情只能从
   positionList[i].jobDetailData 读；先按 number 匹配，再退回 jobId。 */
(() => {
  try {
    const state = window.__INITIAL_STATE__ || {};
    const list = Array.isArray(state.positionList) ? state.positionList : [];
    const id = __JOB_ID__;
    let item = list.find(x => x && String(x.number) === id);
    if (!item) item = list.find(x => x && String(x.jobId) === id);
    return JSON.stringify(item || null);
  } catch (e) {
    return JSON.stringify({ __error__: String(e) });
  }
})()

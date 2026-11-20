/* zhaopin:click — 定位卡片并滚到可视区，不做任何点击。
   详情来自 state，点击对读数没有意义；这里只负责让复核页「定位」能看到
   目标卡片，并保持引擎要求的 {index, total} 返回形状。 */
(() => {
  try {
    const state = window.__INITIAL_STATE__ || {};
    const list = Array.isArray(state.positionList) ? state.positionList : [];
    const id = __JOB_ID__;
    let index = list.findIndex(x => x && String(x.number) === id);
    if (index < 0) index = list.findIndex(x => x && String(x.jobId) === id);

    let scrolled = false;
    const cards = document.querySelectorAll('.job-card');
    if (index >= 0 && cards[index] && cards[index].scrollIntoView) {
      cards[index].scrollIntoView({ block: 'center' });
      scrolled = true;
    }
    return JSON.stringify({ index: index, total: list.length, scrolled: scrolled });
  } catch (e) {
    return JSON.stringify({ index: -1, total: 0, scrolled: false, error: String(e) });
  }
})()

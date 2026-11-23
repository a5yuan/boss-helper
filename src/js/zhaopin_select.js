/* zhaopin:select — 把列表里的第 index 个卡片滚到可视区，返回坐标供 CDP 原生点击。
   卡片与 __INITIAL_STATE__.positionList 同序（实测 20:20），但卡片上没有任何 id
   属性，所以只能按序号定位；点完必须回读 selectedJobId 确认点中的是目标岗位，
   确认失败就放弃，绝不能对着错的岗位点「立即投递」。 */
(() => {
  try {
    const cards = document.querySelectorAll('.job-card');
    const index = __INDEX__;
    const el = cards[index];
    if (!el) return JSON.stringify({ ok: false, reason: 'card_not_found', total: cards.length });
    el.scrollIntoView({ block: 'center' });
    const r = el.getBoundingClientRect();
    return JSON.stringify({
      ok: true,
      total: cards.length,
      x: Math.round(r.left + r.width / 2),
      y: Math.round(r.top + r.height / 2),
    });
  } catch (e) {
    return JSON.stringify({ ok: false, reason: 'select_error: ' + String(e) });
  }
})()

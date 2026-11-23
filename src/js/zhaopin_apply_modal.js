/* zhaopin:apply-modal — 点完「立即投递」后读弹窗，不做点击。
   实测文案：「已向对方发送简历和打招呼语」，两个按钮「留在此页」/「继续沟通」。
   弹层 class 没有稳定值，所以先找 role=dialog / class 含 modal|dialog 的可见容器，
   再退到整页找包含确认文案的最小容器；两处都找不到就如实返回 confirmed=false。
   游客点投递会出登录弹层，用登录文案区分，避免把登录框当成投递成功。 */
(() => {
  try {
    const vis = el => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const phrase = /已向.{0,12}(简历|打招呼)/;
    let host = null;

    for (const el of document.querySelectorAll(
        'div[role="dialog"], .a-modal, [class*="modal"], [class*="dialog"]')) {
      if (vis(el) && phrase.test(el.innerText || '')) { host = el; break; }
    }
    if (!host) {
      for (const el of document.querySelectorAll('div')) {
        if (!vis(el)) continue;
        const t = (el.innerText || '').trim();
        if (t.length <= 300 && phrase.test(t)) { host = el; break; }
      }
    }
    if (!host) {
      const body = document.body.innerText || '';
      return JSON.stringify({
        confirmed: false,
        login: /登录|扫码/.test(body) && !phrase.test(body),
        text: '',
      });
    }

    const text = (host.innerText || '').trim().slice(0, 300);
    const pick = label => {
      for (const b of host.querySelectorAll('button, a, span, div')) {
        const t = (b.innerText || '').trim();
        if (t !== label || !vis(b)) continue;
        // 取最内层：还有子节点文本正好等于 label 的说明是外层壳子
        if (Array.from(b.children).some(c => (c.innerText || '').trim() === label)) continue;
        const r = b.getBoundingClientRect();
        return {
          found: true,
          text: t,
          x: Math.round(r.left + r.width / 2),
          y: Math.round(r.top + r.height / 2),
        };
      }
      return { found: false };
    };

    return JSON.stringify({
      confirmed: true,
      login: false,
      text: text,
      continue: pick('继续沟通'),
      stay: pick('留在此页'),
    });
  } catch (e) {
    return JSON.stringify({ confirmed: false, reason: 'modal_error: ' + String(e) });
  }
})()

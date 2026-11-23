/* zhaopin:chat-read — 只读聊天页：输入框是否就绪、输入框长度、最近消息、发送按钮坐标。
   智联聊天页的 class 名没有实测样本（需要登录态），所以：
   - 输入框沿用全站通用规则：最后一个可见 textarea / contenteditable；
   - 消息只认 class 含 message / msg / bubble / chat-item 的可见节点；
   - 发送按钮只认可见、文案正好是「发送」的最内层元素。
   任何一项找不到就返回 found/ready=false，调用方据此判失败，不猜。 */
(() => {
  try {
    const vis = el => {
      const r = el.getBoundingClientRect();
      return r.width > 40 && r.height > 8;
    };

    const inputs = Array.from(
      document.querySelectorAll('textarea, [contenteditable="true"]')).filter(vis);
    const input = inputs.length ? inputs[inputs.length - 1] : null;
    let inputLen = -1;
    if (input) {
      const raw = ('value' in input) ? input.value : input.innerText;
      inputLen = (raw || '').length;
    }

    const raw = [];
    for (const el of document.querySelectorAll(
        '[class*="message"], [class*="msg"], [class*="bubble"], [class*="chat-item"]')) {
      if (!vis(el)) continue;
      const t = (el.innerText || '').trim();
      if (t && t.length <= 500) raw.push(t);
    }
    // 只留最内层文本，避免外层容器把整段聊天记录当成一条消息
    const messages = raw.filter(t => !raw.some(u => u !== t && t.includes(u))).slice(-20);

    let send = { found: false };
    for (const el of document.querySelectorAll('button, a, [role="button"], div, span')) {
      const t = (el.innerText || '').trim().replace(/\s/g, '');
      if (t !== '发送' || !vis(el)) continue;
      if (Array.from(el.children).some(c =>
          (c.innerText || '').trim().replace(/\s/g, '') === '发送')) continue;
      const r = el.getBoundingClientRect();
      send = {
        found: true,
        x: Math.round(r.left + r.width / 2),
        y: Math.round(r.top + r.height / 2),
      };
      break;
    }

    return JSON.stringify({
      ok: true,
      input_ready: !!input,
      input_len: inputLen,
      messages: messages,
      send: send,
    });
  } catch (e) {
    return JSON.stringify({ ok: false, reason: 'chat_read_error: ' + String(e) });
  }
})()

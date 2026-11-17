(() => {
    // 把招呼语写进最后一个可见输入框（textarea 或 contenteditable）。
    // 依赖：BOSS 聊天页 DOM。只填不发送——不点发送按钮、不触发 Enter。
    const text = __TEXT__;
    const vis = el => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        return r.width > 40 && r.height > 8;
    };
    const nodes = Array.from(document.querySelectorAll('textarea, [contenteditable="true"]')).filter(vis);
    if (!nodes.length) {
        return JSON.stringify({ ok: false, reason: '页面上没有可输入的聊天框，请先打开一个聊天会话' });
    }
    const el = nodes[nodes.length - 1];
    try {
        el.focus();
        if (el.tagName === 'TEXTAREA') {
            const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
            setter.call(el, text);
        } else {
            el.innerText = text;
            el.dispatchEvent(new InputEvent('input', { bubbles: true, data: text, inputType: 'insertText' }));
        }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    } catch (e) {
        return JSON.stringify({ ok: false, reason: '写入失败: ' + (e && e.message ? e.message : e) });
    }
    return JSON.stringify({
        ok: true,
        tag: el.tagName,
        length: (el.value || el.innerText || '').length,
        placeholder: el.getAttribute('placeholder') || '',
    });
})()

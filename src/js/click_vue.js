(async () => {
    const TARGET = '__SID__';
    const cards = document.querySelectorAll('.job-card-box,.job-card-wrap,.job-card,[class*="job-card"]');

    for (const card of cards) {
        if (card.__vue__) {
            const vm = card.__vue__;
            const pdRaw = vm.$options ? (vm.$options.propsData || vm.$props) : null;
            const pd = pdRaw ? (pdRaw.data || pdRaw) : null;
            if (pd && pd.securityId === TARGET) {
                if (typeof vm.clickJobCard === 'function') {
                    try {
                        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        await new Promise(r => setTimeout(r, 600));
                        vm.clickJobCard(pd);
                        return JSON.stringify({ok: true, method: 'vue', index: 0});
                    } catch(e) {
                        return JSON.stringify({ok: false, reason: e.message});
                    }
                }
            }
        }
    }

    const seen = new Set();
    const checkEl = async (el) => {
        const vm = el.__vue__;
        if (!vm || seen.has(vm._uid)) return null;
        seen.add(vm._uid);
        const pdRaw = vm.$options ? (vm.$options.propsData || vm.$props) : null;
        const pd = pdRaw ? (pdRaw.data || pdRaw) : null;
        if (pd && pd.securityId === TARGET) {
            if (typeof vm.clickJobCard === 'function') {
                try {
                    if (el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    await new Promise(r => setTimeout(r, 600));
                    vm.clickJobCard(pd);
                    return JSON.stringify({ok: true, method: 'vue', index: 0});
                } catch(e) {}
            }
            let cur = vm.$parent; let depth = 0;
            while (cur && depth < 5) {
                if (typeof cur.clickJobCard === 'function') {
                    try {
                        // 如果是父组件点击，依然尝试滚动当前元素
                        if (el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        await new Promise(r => setTimeout(r, 600));
                        cur.clickJobCard(pd);
                        return JSON.stringify({ok: true, method: 'vue', index: 0});
                    } catch(e) {}
                }
                cur = cur.$parent; depth++;
            }
        }
        return null;
    };

    let res = await checkEl(document.body);
    if (res) return res;

    const allEls = document.querySelectorAll('*');
    for (const el of allEls) {
        res = await checkEl(el);
        if (res) return res;
    }
    return JSON.stringify({ok: false, reason: 'not_found'});
})()

(() => {
    const TARGET = '__SID__';
    const cards = document.querySelectorAll('.job-card-box');
    for (let i = 0; i < cards.length; i++) {
        const card = cards[i];
        const vm = card.__vue__ || (card.parentElement && card.parentElement.__vue__);
        let matched = false;
        if (vm) {
            const d = vm.$options?.propsData?.data || vm.$props?.data || {};
            if (d.securityId === TARGET) matched = true;
        }
        if (!matched) {
            const children = card.querySelectorAll('*');
            for (const child of children) {
                const cvm = child.__vue__;
                if (cvm) {
                    const d = cvm.$options?.propsData?.data || cvm.$props?.data || {};
                    if (d.securityId === TARGET) { matched = true; break; }
                }
            }
        }
        if (matched) {
            card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            setTimeout(() => card.click(), 300);
            return JSON.stringify({found: true, index: i, total: cards.length});
        }
    }
    return JSON.stringify({found: false, total: cards.length});
})()

(() => {
    const jobs = [];
    const seen = new Set();
    const allEls = document.querySelectorAll('*');

    for (const el of allEls) {
        const vm = el.__vue__;
        if (!vm) continue;
        if (seen.has(vm._uid)) continue;
        seen.add(vm._uid);

        const propsData = vm.$options?.propsData || vm.$props || {};
        const innerData = propsData.data;

        if (innerData && innerData.securityId && innerData.jobName) {
            jobs.push({
                securityId: innerData.securityId,
                jobName: innerData.jobName,
                salaryDesc: innerData.salaryDesc || '',
                areaDistrict: innerData.areaDistrict || '',
                brandName: innerData.brandName || '',
            });
        }

        if (jobs.length >= 300) break;
    }
    return JSON.stringify(jobs);
})()

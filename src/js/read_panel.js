(() => {
    const TARGET = '__SID__';
    function safe(s, limit) {
        if (s == null) return '';
        if (typeof s === 'object') return JSON.stringify(s).slice(0, limit || 200);
        return String(s).slice(0, limit || 200);
    }
    function safeList(arr) {
        if (!Array.isArray(arr)) return [];
        return arr.slice(0, 20).map(v => typeof v === 'object' ? JSON.stringify(v).slice(0, 50) : String(v));
    }
    var main = document.querySelector('.page-jobs-main');
    if (main && main.__vue__) {
        var vm = main.__vue__;
        var cj = (vm.$data || {}).currentJob;
        if (cj && cj.securityId === TARGET) {
            var result = {
                found: true, sid: cj.securityId || '',
                encryptJobId: cj.encryptJobId || '',
                jobName: safe(cj.jobName),
                salaryDesc: safe(cj.salaryDesc),
                locationName: (cj.cityName || '') + (cj.areaDistrict ? ' ' + cj.areaDistrict : ''),
                experienceName: safe(cj.jobExperience),
                degreeName: safe(cj.jobDegree),
                address: [cj.cityName, cj.areaDistrict, cj.businessDistrict].filter(Boolean).join(' '),
                longitude: cj.gps ? cj.gps.longitude : null,
                latitude: cj.gps ? cj.gps.latitude : null,
                bossName: safe(cj.bossName),
                bossTitle: safe(cj.bossTitle),
                bossActiveTime: safe(cj.bossActiveTime),
                brandName: safe(cj.brandName),
                brandStageName: safe(cj.brandStageName),
                brandScaleName: safe(cj.brandScaleName),
                brandIndustry: safe(cj.brandIndustry),
                brandLabels: safeList(cj.brandLabels || []),
                skills: safeList(cj.skills || []),
                welfareList: safeList(cj.welfareList || []),
                jobLabels: safeList(cj.jobLabels || []),
                jobDescription: safe(cj.jobDescription, 3000),
            };
            __EXTRA__
            return JSON.stringify(result);
        }
    }
    var seen = new Set();
    var allEls = document.querySelectorAll('*');
    for (var i = 0; i < allEls.length; i++) {
        var el = allEls[i];
        var v = el.__vue__;
        if (!v || seen.has(v._uid)) continue;
        seen.add(v._uid);
        var cj2 = (v.$data || {}).currentJob;
        if (cj2 && cj2.securityId === TARGET) {
            var result = {
                found: true, sid: cj2.securityId || '',
                jobName: safe(cj2.jobName),
                salaryDesc: safe(cj2.salaryDesc),
                locationName: (cj2.cityName || '') + (cj2.areaDistrict ? ' ' + cj2.areaDistrict : ''),
                experienceName: safe(cj2.jobExperience),
                degreeName: safe(cj2.jobDegree),
                address: [cj2.cityName, cj2.areaDistrict, cj2.businessDistrict].filter(Boolean).join(' '),
                longitude: cj2.gps ? cj2.gps.longitude : null,
                latitude: cj2.gps ? cj2.gps.latitude : null,
                bossName: safe(cj2.bossName),
                bossTitle: safe(cj2.bossTitle),
                bossActiveTime: safe(cj2.bossActiveTime),
                brandName: safe(cj2.brandName),
                brandStageName: safe(cj2.brandStageName),
                brandScaleName: safe(cj2.brandScaleName),
                brandIndustry: safe(cj2.brandIndustry),
                brandLabels: safeList(cj2.brandLabels || []),
                skills: safeList(cj2.skills || []),
                welfareList: safeList(cj2.welfareList || []),
                jobLabels: safeList(cj2.jobLabels || []),
                jobDescription: safe(cj2.jobDescription, 3000),
            };
            __EXTRA__
            return JSON.stringify(result);
        }
    }
    return JSON.stringify({ found: false });
})()

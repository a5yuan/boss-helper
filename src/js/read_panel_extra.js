
            // 读取异步到位的 jobDetail（JD + 公司介绍）
            var pm = (vm.$data || {}).jobDetail;
            if (pm && pm.jobInfo && pm.jobInfo.postDescription) {
                var ji = pm.jobInfo;
                var bc = pm.brandComInfo || {};
                var jdData = {
                    postDescription: safe(ji.postDescription, 5000),
                    introduce: safe(bc.introduce, 2000),
                    stageName: safe(bc.stageName),
                    scaleName: safe(bc.scaleName),
                    industryName: safe(bc.industryName),
                    labels: safeList(bc.labels || []),
                };
                Object.assign(result, jdData);
            }
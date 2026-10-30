import json
import time

from src.core.js_loader import load_js


class VueExtractor:
    """从 Vue 2 组件树中提取岗位的 securityId（仅依赖 extract_list.js）"""

    @staticmethod
    def extract(chrome):
        """返回包含 securityId 的岗位列表"""
        result = chrome.evaluate(load_js("extract_list.js"))
        raw = chrome.get_value(result)
        if isinstance(raw, str):
            return json.loads(raw or "[]")
        return raw if raw is not None else []



# DetailPanelReader：从页面 Vue 状态 ($data.currentJob / $data.jobDetail) 读取。


class DetailPanelReader:
    """
    渲染层本地提取方案 

    关键发现（来自 find_jd_company_intro.py 诊断）：
      - $data.currentJob           → ✅ 同步到位（薪资/boss/品牌/技能/福利）
      - $data.jobDetail.jobInfo    → ✅ 异步稍晚（JD 明文 postDescription）
      - $data.jobDetail.brandComInfo → ✅ 异步稍晚（公司介绍 introduce）

    两者是同一个 .page-jobs-main 组件里的平行属性，加载时机不同。
    提取策略：
      1. 先读 currentJob（250ms 轮询，~1-2 轮即命中）
      2. currentJob 命中后，继续等待 jobDetail（最多再等 3 轮 / ~1.5s）
      3. jobDetail 就位后合并 JD + 公司介绍，写入 output

    数据来源：浏览器本地 Vue 实例状态
    """

    @staticmethod
    def _make_panel_js(target_sid, include_job_detail=False):
        sid_e = target_sid.replace("\\", "\\\\").replace("'", "\\'")
        extra = load_js("read_panel_extra.js") if include_job_detail else ""
        return load_js("read_panel.js", {"'__SID__'": f"'{sid_e}'", "__EXTRA__": extra})

    @staticmethod
    def read_detail(chrome, target_sid, max_wait=3.5):
        """
        V14 方案 E 优化版：
          - 0s 初始延迟（即刻开始轮询）
          - 0.15s 快速步长（响应更敏捷）
          - SID 强校验（确保数据归属）
        """
        import sys
        STEP = 0.15
        
        sys.stdout.write("      [")
        sys.stdout.flush()

        # --- 阶段1: 快速探测 currentJob ---
        elapsed = 0.0
        base_data = None
        while elapsed < max_wait:
            js = DetailPanelReader._make_panel_js(target_sid, include_job_detail=False)
            result = chrome.evaluate(js)
            raw = chrome.get_value(result)
            if isinstance(raw, str):
                parsed = json.loads(raw or "{}")
            else:
                parsed = raw if raw is not None else {}
            
            if parsed.get("found"):
                base_data = parsed
                break
            
            time.sleep(STEP)
            elapsed += STEP

        if not base_data:
            sys.stdout.write("超时]\n")
            sys.stdout.flush()
            return {"error": "timeout", "message": f"详情面板未更新 ({max_wait}s)"}

        # --- 阶段2: 探测异步到位的 jobDetail (JD/介绍) ---
        # 即使 base_data 到了，JD 可能还在路上，我们再给点缓冲时间
        jd_max_wait = 2.0 
        jd_elapsed = 0.0
        final_data = base_data
        
        while jd_elapsed < jd_max_wait:
            js2 = DetailPanelReader._make_panel_js(target_sid, include_job_detail=True)
            result2 = chrome.evaluate(js2)
            raw2 = chrome.get_value(result2)
            if isinstance(raw2, str):
                parsed2 = json.loads(raw2 or "{}")
            else:
                parsed2 = raw2 if raw2 is not None else {}
            
            if parsed2.get("found") and (parsed2.get("postDescription") or parsed2.get("introduce")):
                final_data = parsed2
                break
            
            time.sleep(STEP)
            jd_elapsed += STEP

        sys.stdout.write(f"OK {elapsed+jd_elapsed:.1f}s]\n")
        sys.stdout.flush()

        return {
            "success": True,
            "source": "currentJob+jobDetail",
            "security_id": final_data.get("sid", ""),
            "encrypt_job_id": final_data.get("encryptJobId", ""),
            "title":       final_data.get("jobName", ""),
            "salary":      final_data.get("salaryDesc", ""),
            "location":    final_data.get("locationName", ""),
            "experience":   final_data.get("experienceName", ""),
            "degree":      final_data.get("degreeName", ""),
            "jd":          final_data.get("postDescription", "") or final_data.get("jobDescription", ""),
            "skills":      final_data.get("skills", []),
            "welfare":     final_data.get("welfareList", []),
            "job_labels":  final_data.get("jobLabels", []),
            "address":     final_data.get("address", ""),
            "longitude":   final_data.get("longitude"),
            "latitude":    final_data.get("latitude"),
            "boss_name":   final_data.get("bossName", ""),
            "boss_title":  final_data.get("bossTitle", ""),
            "boss_active": final_data.get("bossActiveTime", ""),
            "company":     final_data.get("brandName", ""),
            "company_stage":  final_data.get("brandStageName", ""),
            "company_scale":  final_data.get("brandScaleName", ""),
            "industry":    final_data.get("industryName") or final_data.get("brandIndustry", ""),
            "company_intro": final_data.get("introduce", ""),
            "company_labels": final_data.get("labels") or final_data.get("brandLabels", []),
        }




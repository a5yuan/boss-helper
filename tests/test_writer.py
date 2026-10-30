"""输出写入与查重口径的单元测试。

运行：
    .venv/Scripts/python -m unittest discover -s tests -v
"""
import json
import os
import tempfile
import unittest

from src.storage.writer import OutputWriter


def _job(title="后端工程师", company="示例公司", location="北京·朝阳区", eid="eid-1"):
    return {
        "title": title,
        "company": company,
        "location": location,
        "encrypt_job_id": eid,
        "salary": "20-30K",
        "jd": "示例 JD",
    }


class TestOutputWriter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.writer = OutputWriter(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_job_writes_json_and_md(self):
        self.writer.save_job(_job(), 1)
        with open(self.writer.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertTrue(os.path.exists(self.writer.md_path))

    def test_same_title_company_and_area_is_duplicate(self):
        self.writer.save_job(_job(), 1)
        self.assertTrue(self.writer.is_duplicate("后端工程师", "示例公司", "朝阳区"))

    def test_same_title_company_without_area_is_duplicate(self):
        self.writer.save_job(_job(), 1)
        self.assertTrue(self.writer.is_duplicate("后端工程师", "示例公司"))

    def test_different_area_is_not_duplicate(self):
        self.writer.save_job(_job(location="北京·朝阳区"), 1)
        self.assertFalse(self.writer.is_duplicate("后端工程师", "示例公司", "海淀区"))

    def test_missing_area_on_existing_job_falls_back_to_duplicate(self):
        self.writer.save_job(_job(location="北京"), 1)
        self.assertTrue(self.writer.is_duplicate("后端工程师", "示例公司", "海淀区"))

    def test_has_job_id(self):
        self.writer.save_job(_job(eid="eid-1"), 1)
        self.assertTrue(self.writer.has_job_id("eid-1"))
        self.assertFalse(self.writer.has_job_id("eid-2"))
        self.assertFalse(self.writer.has_job_id(""))

    def test_old_records_without_job_id_do_not_crash(self):
        self.writer.save_job({"title": "旧岗位", "company": "旧公司"}, 1)
        self.assertFalse(self.writer.has_job_id("eid-x"))
        self.assertTrue(self.writer.is_duplicate("旧岗位", "旧公司"))


if __name__ == "__main__":
    unittest.main()

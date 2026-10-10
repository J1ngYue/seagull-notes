"""测试配置：把 HOME 指到临时目录，别污染真实数据库。"""

import os
import sys
import tempfile
from pathlib import Path

# 必须在导入 seagull_notes 之前设好，config 是模块级读环境变量
_TMP = Path(tempfile.mkdtemp(prefix="seagull-test-"))
os.environ["SEAGULL_NOTES_HOME"] = str(_TMP)
os.environ["SEAGULL_NOTES_LLM_API_KEY"] = ""       # 强制走降级模式

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest                                            # noqa: E402


@pytest.fixture(autouse=True)
def _clean_db():
    """每个测试开跑前清空所有表，保证互不干扰。"""
    from seagull_notes import storage

    with storage._connect() as conn:
        conn.execute("DELETE FROM jobs")
        conn.execute("DELETE FROM notes")
        conn.execute("DELETE FROM transcripts")
    yield

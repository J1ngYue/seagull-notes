"""Seagull Notes - 配置与路径。

模型、数据库与媒体默认落在项目目录，可通过环境变量指定位置。
"""

from __future__ import annotations

import os
from pathlib import Path

# --- 项目根：默认源码所在项目，可用环境变量覆盖 ---
HOME = Path(os.environ.get("SEAGULL_NOTES_HOME", str(Path(__file__).resolve().parents[2])))

MODELS_DIR = HOME / "models"
DATA_DIR = HOME / "data"
MEDIA_DIR = DATA_DIR / "media"
ARTIFACT_DIR = DATA_DIR / "artifacts"
DB_PATH = DATA_DIR / "seagull.db"

# 从浏览器导出的 cookies（一次性导出，之后自动复用）
# B站 的 AI 字幕、会员视频、YouTube 反爬都需要登录态
COOKIE_FILE = DATA_DIR / "cookies.txt"

# --- HuggingFace 缓存：显式锁到 E 盘 ---
HF_HOME = MODELS_DIR / "hf"
HF_HUB_CACHE = HF_HOME / "hub"

# --- ASR 模型 ---
# large-v3 是默认；显存不够或想跑快点可以降到 medium / small
ASR_MODEL = os.environ.get("SEAGULL_NOTES_ASR_MODEL", "large-v3")
ASR_DEVICE = os.environ.get("SEAGULL_NOTES_ASR_DEVICE", "cuda")
ASR_COMPUTE_TYPE = os.environ.get("SEAGULL_NOTES_ASR_COMPUTE", "float16")

# --- LLM 生成 ---
# 留空则使用内置的"无 LLM 降级模式"：直接输出转写稿的结构化 Markdown
LLM_BASE_URL = os.environ.get("SEAGULL_NOTES_LLM_BASE_URL", "https://api.anthropic.com")
LLM_API_KEY = os.environ.get("SEAGULL_NOTES_LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.environ.get("SEAGULL_NOTES_LLM_MODEL", "claude-opus-5")

# --- 代理绕行 ---
# 中国大陆的视频/内容站必须直连。走代理会让对方看到境外机房 IP，
# 触发风控（B站 直接返回 412）。境外站（YouTube 等）则相反，必须走代理。
# 这里列出需要"强制直连"的域名关键词。
DIRECT_DOMAINS = (
    "bilibili.com", "b23.tv", "hdslb.com",
    "douyin.com", "ixigua.com", "kuaishou.com",
    "zhihu.com", "weibo.com", "xiaohongshu.com",
    "qq.com", "163.com", "sina.com.cn", "sohu.com",
    "youku.com", "iqiyi.com", "mgtv.com", "le.com",
    "csdn.net", "jianshu.com", "cnblogs.com", "gitee.com",
)

# 强制直连用的本机 IP。留空则自动探测物理网卡。
# 设成 "auto" 或具体 IP（比如 192.168.1.100）都可。
DIRECT_BIND_ADDRESS = os.environ.get("SEAGULL_NOTES_DIRECT_BIND", "auto")


def needs_direct(url: str) -> bool:
    """这个 URL 是不是必须直连（不能走代理）。

    按域名边界匹配，不能用子串——"le.com" 会误伤 "example.com"。
    """
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False

    return any(host == d or host.endswith("." + d) for d in DIRECT_DOMAINS)


def find_physical_ip() -> str | None:
    """找一个物理网卡的 IPv4 地址，用来绕过 TUN 隧道。

    典型场景：机器上开着 Clash Verge 的 TUN 模式，默认路由全部走虚拟网卡。
    绑定到物理网卡的地址就能让流量走真实网络出口。

    返回 None 表示没找到（可能没开代理，也可能探测失败）。
    """
    import socket

    if DIRECT_BIND_ADDRESS and DIRECT_BIND_ADDRESS != "auto":
        return DIRECT_BIND_ADDRESS

    candidates: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith(("127.", "169.254.", "0.")):
                continue
            candidates.append(ip)
    except OSError:
        return None

    # TUN 隧道常见网段（Clash / sing-box 默认），优先排除
    tun_prefixes = ("172.19.", "172.18.", "198.18.", "198.19.")

    def score(ip: str) -> int:
        if any(ip.startswith(p) for p in tun_prefixes):
            return 100                      # 最差，基本确定是 TUN
        if ip.startswith("192.168."):
            return 0                        # 家用网段，最可能对
        if ip.startswith("10."):
            return 10
        if ip.startswith("172."):
            return 20
        return 5

    if not candidates:
        return None
    return min(candidates, key=score)


# --- 导出 ---
EXPORT_LINK_TTL_SECONDS = 600       # 产物下载链接有效期，学 CuteNote 的短时效
JOB_POLL_BACKOFF = [2, 4, 8, 10]    # 轮询退避序列（秒），和 CuteNote 一致的节奏
JOB_MAX_WAIT_SECONDS = 1800         # 客户端侧等待上限，超时不代表服务端取消


def ensure_dirs() -> None:
    """建好所有需要的目录。幂等。"""
    for d in (MODELS_DIR, DATA_DIR, MEDIA_DIR, ARTIFACT_DIR, HF_HOME, HF_HUB_CACHE):
        d.mkdir(parents=True, exist_ok=True)


def apply_hf_env() -> None:
    """把 HuggingFace 环境变量钉死到 E 盘。

    faster-whisper 首次运行会去 HuggingFace 拉模型，不设这个就默认落 C 盘。
    """
    os.environ.setdefault("HF_HOME", str(HF_HOME))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(HF_HUB_CACHE))
    # 国内网络访问 huggingface.co 基本不通，默认走镜像
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

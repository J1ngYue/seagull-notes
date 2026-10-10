#!/usr/bin/env python3
"""一次性导出浏览器 cookies，供后续自动复用。

B站 的 AI 字幕、会员视频，以及 YouTube 对匿名请求的反爬，都需要登录态。
与其每次跑都去读浏览器（浏览器开着时读不了），不如导出一次存起来。

用法：
    python setup_cookies.py edge      # 从 Edge 导出
    python setup_cookies.py chrome    # 从 Chrome 导出
    python setup_cookies.py list      # 看看导出的文件里有什么

导出后 fetch.py 会自动使用，不用再传任何参数。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_HOME = Path(os.environ.get("SEAGULL_NOTES_HOME", str(Path(__file__).resolve().parents[2])))
SRC_DIR = PROJECT_HOME / "src"

if str(SRC_DIR) not in sys.path and SRC_DIR.is_dir():
    sys.path.insert(0, str(SRC_DIR))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BROWSERS = ("edge", "chrome", "firefox", "brave", "chromium", "opera", "vivaldi", "safari")

# 关心的站点（只是用来报告，实际是全量导出）
INTERESTING = ("bilibili", "youtube", "youtu.be", "douyin", "zhihu", "weibo")


def _load_cookies(browser: str):
    """从浏览器读 cookie。浏览器开着时会失败。"""
    from yt_dlp.cookies import extract_cookies_from_browser

    class _Quiet:
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass

    return extract_cookies_from_browser(browser, logger=_Quiet())


def _save_jar(jar, path: Path) -> int:
    """写成 Netscape 格式的 cookies.txt。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    jar.save(str(path), ignore_discard=True, ignore_expires=True)
    return len(list(jar))


def _summarize(path: Path) -> dict:
    """统计导出的 cookie 里有哪些关心的站点。"""
    hosts: dict[str, int] = {}
    if not path.exists():
        return hosts
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        host = parts[0].lstrip(".")
        for key in INTERESTING:
            if key in host:
                hosts[key] = hosts.get(key, 0) + 1
                break
    return hosts


def cmd_export(browser: str) -> int:
    from seagull_notes import config

    print(f"从 {browser} 读取 cookies……")
    try:
        jar = _load_cookies(browser)
    except Exception as exc:                                    # noqa: BLE001
        message = str(exc)
        print(f"\n✗ 读取失败：{message[:300]}\n")
        if "could not copy" in message.lower() or "unable to" in message.lower():
            print("这通常是因为浏览器正在运行，锁住了 cookie 数据库。")
            print(f"\n请把 {browser} 完全关掉（检查任务栏和托盘图标），然后重跑这条命令。")
            print("\n关掉浏览器不影响你已经打开的网页——重新打开就能恢复。")
        else:
            print("确认：1) 浏览器名字拼对了（edge/chrome/firefox）；")
            print("      2) 那个浏览器确实装在这台机器上并且登录过目标网站。")
        return 1

    count = _save_jar(jar, config.COOKIE_FILE)
    print(f"✓ 已导出 {count} 条 cookie")
    print(f"  存放位置：{config.COOKIE_FILE}")

    hosts = _summarize(config.COOKIE_FILE)
    if hosts:
        print("\n  包含这些站点的登录态：")
        for host, n in sorted(hosts.items(), key=lambda kv: -kv[1]):
            print(f"    - {host}: {n} 条")
        if "bilibili" not in hosts and "youtube" not in hosts:
            print("\n  ⚠ 没看到 B站 或 YouTube 的 cookie。确认你在那个浏览器里登录过它们。")
    else:
        print("\n  ⚠ 没识别到常用视频站的 cookie。")
        print("    确认你用的是登录过 B站/YouTube 的那个浏览器。")

    print("\n之后运行 fetch.py 时可以使用这些 cookie；--anonymous 会跳过它们。")
    print("cookie 会过期（通常几周到几个月），失效了重跑这条命令即可。")
    return 0


def cmd_list() -> int:
    from seagull_notes import config

    path = config.COOKIE_FILE
    if not path.exists():
        print(f"还没有导出过 cookies（期望位置：{path}）")
        print(f"先跑：python setup_cookies.py edge")
        return 1

    size = path.stat().st_size
    mtime = path.stat().st_mtime
    import time

    print(f"文件：{path}")
    print(f"大小：{size} 字节")
    print(f"导出时间：{time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))}")

    hosts = _summarize(path)
    if hosts:
        print("\n包含的站点：")
        for host, n in sorted(hosts.items(), key=lambda kv: -kv[1]):
            print(f"  - {host}: {n} 条")

    total = sum(
        1 for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line and not line.startswith("#") and len(line.split("\t")) >= 7
    )
    print(f"\n总 cookie 数：{total}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="setup_cookies.py",
        description="一次性导出浏览器 cookies 供后续复用",
    )
    parser.add_argument("browser", nargs="?", default="edge", choices=(*BROWSERS, "list"),
                        help="浏览器名，或 list 查看已导出的内容")
    args = parser.parse_args()

    if args.browser == "list":
        return cmd_list()
    return cmd_export(args.browser)


if __name__ == "__main__":
    raise SystemExit(main())

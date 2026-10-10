#!/usr/bin/env python3
"""内置浏览器登录：开一个我们自己的浏览器，你登录，cookie 自动导出。

为什么不用你现有的浏览器？
  Chrome/Edge 从 127 版起启用了 App-Bound Encryption，cookie 加密密钥
  绑定在浏览器进程上，外部程序（包括 yt-dlp）解不开。
  而这里是我们自己启动的浏览器——cookie 通过浏览器自己的接口读出来，
  根本没经过解密这一步，那道墙就不存在了。

用法：
    python login.py bilibili
    python login.py youtube
    python login.py status      # 看看现在有没有 cookie
"""

from __future__ import annotations

import argparse
import os
import sys
import time
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

# 专属浏览器配置目录（登录状态存在这里，第二次打开还是登录着的）
PROFILE_DIR = PROJECT_HOME / "data" / "browser-profile"

LOGIN_TIMEOUT_SECONDS = 300     # 5 分钟不登录就放弃
POLL_INTERVAL = 2.0


# ---------------------------------------------------------------- 站点定义

def _has_cookie(cookies, names) -> bool:
    got = {c.get("name") for c in cookies}
    return any(n in got for n in names)


SITES: dict[str, dict] = {
    "bilibili": {
        "url": "https://www.bilibili.com/",
        # SESSDATA 是 B站 的登录凭证；DedeUserID 也一起验一下更稳
        "login_cookies": ("SESSDATA",),
        "label": "B站",
        "note": "扫码或账号密码登录都行。登录成功后浏览器会自动关闭。",
    },
    "youtube": {
        "url": "https://www.youtube.com/",
        "login_cookies": ("SAPISID", "__Secure-1PAPISID", "LOGIN_INFO"),
        "label": "YouTube",
        "note": "登录成功后浏览器会自动关闭。",
    },
    "zhihu": {
        "url": "https://www.zhihu.com/",
        "login_cookies": ("z_c0",),
        "label": "知乎",
        "note": "登录成功后浏览器会自动关闭。",
    },
}


# ---------------------------------------------------------------- cookie 导出

def _write_netscape(cookies: list[dict], path: Path) -> int:
    """写 Netscape 格式的 cookies.txt（yt-dlp 认这个格式）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Netscape HTTP Cookie File",
        "# 由 seagull-notes 的内置浏览器登录导出",
        "",
    ]
    count = 0
    for c in cookies:
        domain = c.get("domain") or ""
        if not domain:
            continue
        name = c.get("name") or ""
        value = c.get("value") or ""
        if not name:
            continue

        flag = "TRUE" if domain.startswith(".") else "FALSE"
        secure = "TRUE" if c.get("secure") else "FALSE"
        path_val = c.get("path") or "/"
        expires = c.get("expires")
        try:
            expires = int(expires) if expires and expires > 0 else 0
        except (TypeError, ValueError):
            expires = 0

        lines.append(
            f"{domain}\t{flag}\t{path_val}\t{secure}\t{expires}\t{name}\t{value}"
        )
        count += 1

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def _load_existing(path: Path) -> dict[str, int]:
    """统计已有 cookies.txt 里的站点分布。"""
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
        hosts[host] = hosts.get(host, 0) + 1
    return hosts


# ---------------------------------------------------------------- 主流程

def do_login(site_key: str) -> int:
    from seagull_notes import config

    site = SITES[site_key]
    label = site["label"]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("✗ 没装 playwright。先跑：")
        print(f"    {sys.executable} -m pip install playwright")
        print(f"    {sys.executable} -m playwright install chromium")
        return 2

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"打开内置浏览器，前往 {label}……")
    print(f"  浏览器配置目录：{PROFILE_DIR}")
    print()

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                viewport={"width": 1280, "height": 860},
                locale="zh-CN",
                args=[
                    # 少一点自动化痕迹，降低被风控盯上的概率
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
        except Exception as exc:                                # noqa: BLE001
            message = str(exc)
            print(f"✗ 启动浏览器失败：{message[:300]}\n")
            if "Executable doesn't exist" in message or "playwright install" in message:
                print("Chromium 还没下载。跑这个：")
                print(f"    {sys.executable} -m playwright install chromium")
            return 2

        page = context.pages[0] if context.pages else context.new_page()

        # 先看是不是已经登录过（profile 是持久的）
        try:
            existing = context.cookies()
        except Exception:                                       # noqa: BLE001
            existing = []

        if _has_cookie(existing, site["login_cookies"]):
            print(f"✓ 这个浏览器已经登录过 {label} 了，直接导出。")
            return _finish(context, config, label)

        try:
            page.goto(site["url"], timeout=60000, wait_until="domcontentloaded")
        except Exception as exc:                                # noqa: BLE001
            print(f"  页面加载慢或无响应（{type(exc).__name__}），继续等……")

        print(f"👉 请在打开的浏览器窗口里登录 {label}")
        print(f"   {site['note']}")
        print(f"   最多等 {LOGIN_TIMEOUT_SECONDS // 60} 分钟。想放弃就直接关掉那个窗口。")
        print()

        started = time.time()
        last_tick = 0
        while True:
            if time.time() - started > LOGIN_TIMEOUT_SECONDS:
                print(f"\n✗ 等太久了（{LOGIN_TIMEOUT_SECONDS // 60} 分钟还没检测到登录）。")
                print("  重新跑一次这条命令即可。")
                context.close()
                return 1

            try:
                cookies = context.cookies()
            except Exception:                                   # noqa: BLE001
                print("\n  浏览器被关掉了，退出。")
                return 1

            if _has_cookie(cookies, site["login_cookies"]):
                print(f"\n✓ 检测到 {label} 登录成功！")
                time.sleep(1.0)         # 等一下，让浏览器把其余 cookie 也写完
                return _finish(context, config, label)

            elapsed = int(time.time() - started)
            if elapsed // 15 > last_tick:
                last_tick = elapsed // 15
                print(f"  …等待登录中（已等 {elapsed} 秒）")

            time.sleep(POLL_INTERVAL)


def _finish(context, config, label: str) -> int:
    """导出 cookie 并收尾。"""
    try:
        cookies = context.cookies()
    except Exception as exc:                                    # noqa: BLE001
        print(f"✗ 读取 cookie 失败：{exc}")
        return 1
    finally:
        try:
            context.close()
        except Exception:                                       # noqa: BLE001
            pass

    count = _write_netscape(cookies, config.COOKIE_FILE)
    print(f"✓ 已导出 {count} 条 cookie")
    print(f"  {config.COOKIE_FILE}")

    hosts = _load_existing(config.COOKIE_FILE)
    if hosts:
        interesting = {k: v for k, v in hosts.items()
                       if any(s in k for s in ("bilibili", "youtube", "zhihu"))}
        if interesting:
            print("\n  包含：")
            for host, n in sorted(interesting.items(), key=lambda kv: -kv[1])[:8]:
                print(f"    - {host}: {n} 条")

    print(f"\n之后 fetch.cmd 会自动带上这些 cookie，不用再加参数。")
    print("cookie 会过期（几周到几个月）。失效了就重跑这条命令。")
    return 0


def do_status() -> int:
    from seagull_notes import config

    path = config.COOKIE_FILE
    if not path.exists():
        print(f"还没有 cookie（期望位置：{path}）")
        print("跑：scripts\\login.cmd bilibili")
        return 1

    import time as _t

    stat = path.stat()
    print(f"文件：{path}")
    print(f"导出时间：{_t.strftime('%Y-%m-%d %H:%M', _t.localtime(stat.st_mtime))}")
    print(f"大小：{stat.st_size} 字节")

    hosts = _load_existing(path)
    if hosts:
        print("\n包含的站点：")
        for host, n in sorted(hosts.items(), key=lambda kv: -kv[1])[:15]:
            print(f"  - {host}: {n} 条")

    # 检查关键登录 cookie 在不在
    raw = path.read_text(encoding="utf-8", errors="ignore")
    print("\n关键登录凭证：")
    for name, cookie in (("B站", "SESSDATA"), ("YouTube", "SAPISID"), ("知乎", "z_c0")):
        found = any(
            line.split("\t")[5] == cookie
            for line in raw.splitlines()
            if not line.startswith("#") and len(line.split("\t")) >= 7
        )
        print(f"  {name:8s} {cookie:16s} {'✓ 有' if found else '✗ 无'}")

    print(f"\n浏览器配置目录：{PROFILE_DIR}")
    print("（登录状态存在那里，下次跑 login.cmd 不用重新登录）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="login.py",
        description="打开内置浏览器登录，自动导出 cookie",
    )
    parser.add_argument(
        "site", nargs="?", default="bilibili",
        choices=(*SITES.keys(), "status"),
        help="要登录的站点，或 status 查看当前状态",
    )
    args = parser.parse_args()

    if args.site == "status":
        return do_status()
    return do_login(args.site)


if __name__ == "__main__":
    raise SystemExit(main())

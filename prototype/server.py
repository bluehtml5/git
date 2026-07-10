#!/usr/bin/env python3
"""DeskLite — 把任何有瀏覽器的裝置(iPad / 手機 / 筆電)變成電腦的第二螢幕。

原型架構(對應 DeskIn 的「延伸螢幕」功能):

    [虛擬顯示器] → [畫面擷取 mss] → [JPEG 編碼] → [WebSocket] → [iPad 瀏覽器 canvas]
                                                      ↑
    [作業系統滑鼠事件] ← [XTest 注入] ← [觸控事件回傳] ─┘

在正式產品中,JPEG/WebSocket 會換成硬體 H.264 + WebRTC,
虛擬顯示器會由各平台驅動(Windows IddCx / macOS CGVirtualDisplay)建立;
原型在 Linux 上以 Xvfb 或 xrandr VIRTUAL 輸出充當虛擬顯示器。

用法:
    python3 server.py [--port 8000] [--display :99] [--monitor 1]
                      [--fps 30] [--quality 70]
啟動後用 iPad 的 Safari 掃描終端機顯示的 QR code 即可連線。
"""

import argparse
import asyncio
import io
import json
import os
import socket
import sys
import time
import zlib

from aiohttp import web, WSMsgType

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


# ---------------------------------------------------------------------------
# 畫面擷取
# ---------------------------------------------------------------------------

class ScreenCapturer:
    """用 mss 擷取螢幕(跨平台:Linux/X11、Windows、macOS)。"""

    def __init__(self, monitor_index: int = 1):
        import mss

        self._mss = getattr(mss, "MSS", mss.mss)()
        monitors = self._mss.monitors
        if monitor_index >= len(monitors):
            raise SystemExit(
                f"monitor {monitor_index} 不存在,共 {len(monitors) - 1} 個螢幕"
            )
        self.monitor = monitors[monitor_index]
        self.primary = monitors[1]
        self.width = self.monitor["width"]
        self.height = self.monitor["height"]
        self._last_crc = None

    def grab_jpeg(self, quality: int) -> bytes | None:
        """擷取一張畫面並編成 JPEG;畫面沒變時回傳 None 以節省頻寬。"""
        from PIL import Image

        shot = self._mss.grab(self.monitor)
        crc = zlib.crc32(shot.raw)
        if crc == self._last_crc:
            return None
        self._last_crc = crc

        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()

    def force_keyframe(self):
        self._last_crc = None


# ---------------------------------------------------------------------------
# 輸入注入(把 iPad 上的觸控變成電腦的滑鼠事件)
# ---------------------------------------------------------------------------

class X11Input:
    """Linux:透過 XTest 擴充把觸控事件注入 X server。"""

    def __init__(self):
        from Xlib import display
        from Xlib.ext import xtest

        self._xtest = xtest
        self._display = display.Display()
        if not self._display.has_extension("XTEST"):
            raise RuntimeError("X server 不支援 XTEST 擴充")

    def pointer(self, kind: str, x: int, y: int):
        from Xlib import X

        self._xtest.fake_input(self._display, X.MotionNotify, x=x, y=y)
        if kind == "down":
            self._xtest.fake_input(self._display, X.ButtonPress, 1)
        elif kind == "up":
            self._xtest.fake_input(self._display, X.ButtonRelease, 1)
        self._display.sync()


class PyAutoGUIInput:
    """Windows / macOS:用 pyautogui 注入滑鼠事件。

    macOS Retina 螢幕上 mss 回報的是實體像素、pyautogui 用的是邏輯座標,
    這裡以主螢幕的比例換算(macOS 需在系統設定授權「輔助使用」)。
    """

    def __init__(self, primary_monitor: dict):
        import pyautogui

        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0
        self._gui = pyautogui
        logical_w, logical_h = pyautogui.size()
        self._scale_x = logical_w / primary_monitor["width"]
        self._scale_y = logical_h / primary_monitor["height"]

    def pointer(self, kind: str, x: int, y: int):
        x = int(x * self._scale_x)
        y = int(y * self._scale_y)
        if kind == "down":
            self._gui.mouseDown(x, y)
        elif kind == "up":
            self._gui.mouseUp(x, y)
        else:
            self._gui.moveTo(x, y)


class NullInput:
    """沒有輸入後端時的替代品(僅顯示畫面,不回傳觸控)。"""

    def pointer(self, kind, x, y):
        pass


def make_input_backend(primary_monitor: dict):
    if sys.platform.startswith("linux") and os.environ.get("DISPLAY"):
        try:
            return X11Input()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] XTest 輸入注入不可用:{exc}")
    elif sys.platform in ("win32", "darwin"):
        try:
            return PyAutoGUIInput(primary_monitor)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] pyautogui 輸入注入不可用(pip install pyautogui):{exc}")
    print("[warn] 觸控回傳已停用,僅串流畫面")
    return NullInput()


# ---------------------------------------------------------------------------
# WebSocket 串流
# ---------------------------------------------------------------------------

class StreamServer:
    def __init__(self, capturer: ScreenCapturer, fps: int, quality: int):
        self.capturer = capturer
        self.fps = fps
        self.quality = quality
        self.input_backend = make_input_backend(capturer.primary)
        self.clients: set[web.WebSocketResponse] = set()

    async def broadcast_loop(self):
        interval = 1.0 / self.fps
        loop = asyncio.get_running_loop()
        while True:
            start = time.monotonic()
            if self.clients:
                # JPEG 編碼是 CPU 密集工作,丟到 thread pool 避免卡住事件迴圈
                frame = await loop.run_in_executor(
                    None, self.capturer.grab_jpeg, self.quality
                )
                if frame is not None:
                    dead = set()
                    for ws in self.clients:
                        try:
                            await ws.send_bytes(frame)
                        except (ConnectionError, RuntimeError):
                            dead.add(ws)
                    self.clients -= dead
            elapsed = time.monotonic() - start
            await asyncio.sleep(max(0.0, interval - elapsed))

    async def handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(max_msg_size=4 * 1024 * 1024)
        await ws.prepare(request)
        peer = request.remote
        print(f"[info] 裝置已連線:{peer}(目前 {len(self.clients) + 1} 台)")

        await ws.send_json(
            {
                "type": "config",
                "width": self.capturer.width,
                "height": self.capturer.height,
            }
        )
        self.capturer.force_keyframe()
        self.clients.add(ws)
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                if data.get("type") == "pointer":
                    # 正規化座標 → 該螢幕的絕對桌面座標(延伸桌面要加上螢幕偏移)
                    mon = self.capturer.monitor
                    x = mon["left"] + int(data["x"] * mon["width"])
                    y = mon["top"] + int(data["y"] * mon["height"])
                    self.input_backend.pointer(data["event"], x, y)
                elif data.get("type") == "ping":
                    await ws.send_json({"type": "pong", "t": data.get("t")})
        finally:
            self.clients.discard(ws)
            print(f"[info] 裝置已離線:{peer}")
        return ws


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def print_qr(url: str):
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except Exception:  # noqa: BLE001
        pass


async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--display", help="X display,例如 :99(預設用 $DISPLAY)")
    parser.add_argument("--monitor", type=int, default=1, help="要串流的螢幕編號")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--quality", type=int, default=70, help="JPEG 品質 1-95")
    args = parser.parse_args()

    if args.display:
        os.environ["DISPLAY"] = args.display

    capturer = ScreenCapturer(args.monitor)
    server = StreamServer(capturer, args.fps, args.quality)

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", server.handle_ws)
    app.router.add_static("/static", STATIC_DIR)

    async def on_startup(_app):
        asyncio.get_running_loop().create_task(server.broadcast_loop())

    app.on_startup.append(on_startup)

    url = f"http://{lan_ip()}:{args.port}"
    print(f"DeskLite 已啟動:{capturer.width}x{capturer.height} @ {args.fps}fps")
    print(f"在 iPad 的 Safari 開啟 {url},或掃描 QR code:")
    print_qr(url)

    web.run_app(app, port=args.port, print=None)


if __name__ == "__main__":
    main()

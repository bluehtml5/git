#!/usr/bin/env python3
"""端對端測試:模擬 iPad 客戶端連上 DeskLite 伺服器。

驗證三件事:
1. 能收到 config(遠端螢幕解析度)
2. 能持續收到 JPEG 畫面,且畫面內容正確(存成 PNG 供人工檢查)
3. 送出觸控事件後,X server 的滑鼠游標真的移動到對應座標(輸入注入生效)

用法:先啟動 Xvfb 與 server.py,再執行
    DISPLAY=:99 python3 e2e_test.py ws://127.0.0.1:8000/ws out.png
"""

import asyncio
import io
import json
import sys

import aiohttp


async def run(ws_url: str, png_out: str) -> int:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(ws_url) as ws:
            config = None
            frames = []
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("type") == "config":
                        config = data
                        print(f"[ok] config: {data['width']}x{data['height']}")
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    frames.append(msg.data)
                    if len(frames) >= 1:
                        break
            assert config, "沒收到 config"
            assert frames, "沒收到任何畫面"

            from PIL import Image

            img = Image.open(io.BytesIO(frames[0]))
            assert img.size == (config["width"], config["height"]), (
                f"畫面尺寸 {img.size} 與 config 不符"
            )
            img.save(png_out)
            print(f"[ok] 收到 {len(frames[0])} bytes JPEG,已存 {png_out}")

            # 模擬 iPad 觸控:點擊畫面 (75%, 25%) 的位置
            tap = {"type": "pointer", "x": 0.75, "y": 0.25}
            await ws.send_json({**tap, "event": "down"})
            await ws.send_json({**tap, "event": "up"})
            await asyncio.sleep(0.5)

    # 驗證 X server 的游標真的被移到該座標
    from Xlib import display

    d = display.Display()
    root = d.screen().root
    pointer = root.query_pointer()
    expect_x = int(0.75 * config["width"])
    expect_y = int(0.25 * config["height"])
    assert (pointer.root_x, pointer.root_y) == (expect_x, expect_y), (
        f"游標在 ({pointer.root_x},{pointer.root_y}),預期 ({expect_x},{expect_y})"
    )
    print(f"[ok] 觸控注入成功:游標移動到 ({pointer.root_x},{pointer.root_y})")
    print("[pass] 全部通過")
    return 0


if __name__ == "__main__":
    ws_url = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8000/ws"
    png_out = sys.argv[2] if len(sys.argv) > 2 else "frame.png"
    sys.exit(asyncio.run(run(ws_url, png_out)))

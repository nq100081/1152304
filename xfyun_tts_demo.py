#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
讯飞在线语音合成 Demo (WebSocket API)
======================================
将文本合成为 MP3 音频文件。

使用前请先在 https://console.xfyun.cn/ 注册并创建应用，
获取 APP_ID, API_KEY, API_SECRET，然后填入下方的配置区。
"""

import base64
import hmac
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
from wsgiref.handlers import format_date_time

import websocket  # pip install websocket-client

# ============================================================
# 配置区 — 请替换为你自己的讯飞控制台凭证
# ============================================================
APP_ID = os.environ.get("XFYUN_APP_ID", "31581e3a")
API_KEY = os.environ.get("XFYUN_API_KEY", "72e7a4daf44673aa664c88769d4766c0")
API_SECRET = os.environ.get("XFYUN_API_SECRET", "M2QyMWI5NDIxNGVhYTZiZDBjYjk3OWFk")

# ---- 合成参数 ----
TEXT = "欢迎使用讯飞在线语音合成服务。这是一个Python调用示例。"  # 要合成的文本
VOICE_NAME = "xiaoyan"        # 发音人: xiaoyan(小燕) xiaofeng(小峰) aisjiuxu(许久) aisxmeng(小萌) ...
SPEED = 50                    # 语速 0-100, 默认 50
PITCH = 50                    # 音高 0-100, 默认 50
VOLUME = 50                   # 音量 0-100, 默认 50
AUDIO_ENCODING = "lame"       # 输出格式: lame→MP3, raw→PCM, speex→speex-wb, opus→opus
OUTPUT_FILE = "output.mp3"    # 输出文件名
# ============================================================

# 讯飞 TTS WebSocket 地址
HOST_URL = "wss://tts-api.xfyun.cn/v2/tts"
HOST = urlparse(HOST_URL).hostname
REQUEST_URI = urlparse(HOST_URL).path


def build_auth_url() -> str:
    """
    组装带鉴权签名的 WebSocket URL。

    签名算法 (RFC 汉化):
        1. 生成 RFC 1123 格式日期    →  date
        2. 拼接签名原始字符串          →  host + "\n" + date + "\n" + "GET " + request_uri + " HTTP/1.1"
        3. 用 API_SECRET 做 HMAC-SHA256, 输出 base64
        4. 按格式拼 authorization header

    最终 URL: wss://host/request_uri?authorization=...&date=...&host=host
    """
    # 生成 RFC 1123 GMT 时间
    now = datetime.now(timezone.utc)
    date_str = format_date_time(now.timestamp())

    # 签名原文
    signature_origin = f"host: {HOST}\ndate: {date_str}\nGET {REQUEST_URI} HTTP/1.1"

    # HMAC-SHA256 签名, base64 编码
    signature_sha = hmac.new(
        API_SECRET.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature_base64 = base64.b64encode(signature_sha).decode("utf-8")

    # 拼接 authorization
    authorization_origin = (
        f'api_key="{API_KEY}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature_base64}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

    # 最终 URL 参数
    query = urlencode(
        {
            "authorization": authorization,
            "date": date_str,
            "host": HOST,
        }
    )
    return f"{HOST_URL}?{query}"


def build_request_params() -> dict:
    """构造发送给服务端的业务参数 (JSON)。"""
    return {
        "common": {
            "app_id": APP_ID,
            # uid: 用户唯一标识，这里用随机 UUID
        },
        "business": {
            "aue": AUDIO_ENCODING,  # 音频编码格式
            "sfl": 1,               # 前端点静音跳过（流式时有用）
            "auf": "audio/L16;rate=16000",
            "vcn": VOICE_NAME,      # 发音人
            "speed": SPEED,
            "pitch": PITCH,
            "volume": VOLUME,
            "tte": "utf8",          # 文本编码
        },
        "data": {
            "status": 2,            # 2=一次传完 (非流式)
            "text": base64.b64encode(TEXT.encode("utf-8")).decode("utf-8"),
        },
    }


def synthesize() -> bytes:
    """
    通过 WebSocket 发送合成请求, 返回完整的音频数据 (bytes)。
    """
    url = build_auth_url()
    params = build_request_params()
    audio_chunks: list[bytes] = []

    ws = websocket.WebSocket()
    ws.connect(url)

    # 发送合成参数
    ws.send(json.dumps(params))

    # 循环接收数据
    while True:
        message = ws.recv()
        if isinstance(message, bytes):
            # 纯音频帧
            audio_chunks.append(message)
            continue

        # JSON 响应帧
        resp = json.loads(message)
        code = resp.get("code", -1)

        if code != 0:
            err_msg = resp.get("message", "未知错误")
            sid = resp.get("sid", "")
            raise RuntimeError(f"[sid={sid}] code={code} → {err_msg}")

        data_info = resp.get("data", {})
        status = data_info.get("status", -1)

        audio_payload = data_info.get("audio")
        if audio_payload:
            audio_chunks.append(base64.b64decode(audio_payload))

        cen = data_info.get("cen", {})
        # 可选打印合成信息
        # print(f"  status={status}, cen={cen}")

        if status == 2:  # 合成结束
            break

    ws.close()
    return b"".join(audio_chunks)


def main():
    print("=" * 60)
    print("  讯飞在线语音合成 Demo (WebSocket)")
    print("=" * 60)

    # 快速检查凭证是否已填写
    if "请替换" in APP_ID:
        print("\n⚠️  请先设置讯飞凭证！\n")
        print("方式一 (推荐) — 环境变量:")
        print("  set XFYUN_APP_ID=你的APP_ID")
        print("  set XFYUN_API_KEY=你的API_KEY")
        print("  set XFYUN_API_SECRET=你的API_SECRET\n")
        print("方式二 — 直接修改脚本顶部的 APP_ID / API_KEY / API_SECRET\n")
        print(f"获取凭证: https://console.xfyun.cn/")
        return

    print(f"\n📝 合成文本: {TEXT}")
    print(f"🎤 发音人:   {VOICE_NAME}")
    print(f"🎵 输出格式: {AUDIO_ENCODING}")
    print(f"📁 输出文件: {OUTPUT_FILE}")
    print(f"\n⏳ 正在合成...")

    try:
        audio_data = synthesize()
    except RuntimeError as e:
        print(f"\n❌ 合成失败: {e}")
        return

    with open(OUTPUT_FILE, "wb") as f:
        f.write(audio_data)

    file_size = len(audio_data)
    output_abs = os.path.abspath(OUTPUT_FILE)

    print(f"\n✅ 合成成功！")
    print(f"   文件: {output_abs}")
    print(f"   大小: {file_size / 1024:.1f} KB ({file_size} bytes)")


if __name__ == "__main__":
    main()

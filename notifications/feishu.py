import base64
import hashlib
import hmac
import time

import requests

import config


def send_card(title: str, content: str, *, template: str = "red") -> dict:
    timestamp = int(time.time())
    string_to_sign = f"{timestamp}\n{config.FEISHU_SIGNING_SECRET}".encode()
    sign = base64.b64encode(
        hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    ).decode()
    payload = {
        "timestamp": str(timestamp),
        "sign": sign,
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title,
                },
                "template": template,
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content,
                        "text_align": "left",
                    }
                ],
            },
        },
    }

    response = requests.post(
        config.FEISHU_WEBHOOK_URL,
        json=payload,
        proxies=config.get_proxies(),
        timeout=config.HTTP_TIMEOUT,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 0:
        raise RuntimeError(f"飞书通知发送失败: {result.get('msg')}")
    return result

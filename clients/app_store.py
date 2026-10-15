"""通过 Apple 查询接口获取 App Store 应用的名称与版本。"""

import re

import requests

from config import get_proxies
from models import VersionInfo


def fetch_app_version(app_id: str | int, country: str = "us") -> VersionInfo:
    app_id = str(app_id)
    if not re.fullmatch(r"[0-9]+", app_id) or int(app_id) <= 0:
        raise ValueError("App Store app_id 应为正整数或数字字符串")
    app_id = str(int(app_id))
    if not isinstance(country, str) or not re.fullmatch(r"[A-Za-z]{2}", country):
        raise ValueError("App Store country 应为两位地区代码，例如 us 或 cn")
    country = country.lower()

    response = requests.get(
        "https://itunes.apple.com/lookup",
        params={"id": app_id, "country": country},
        proxies=get_proxies(),
        timeout=(10, 30),
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Apple 查询接口返回了无效的 results")
    app = next(
        (
            result
            for result in data["results"]
            if isinstance(result, dict) and str(result.get("trackId")) == app_id
        ),
        None,
    )
    if app is None:
        raise ValueError(f"App Store {country} 区未找到应用 {app_id}")
    name = app.get("trackName")
    version = app.get("version")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Apple 查询接口缺少有效的 trackName")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Apple 查询接口缺少有效的 version")
    url = app.get("trackViewUrl") or f"https://apps.apple.com/{country}/app/id{app_id}"
    if not isinstance(url, str):
        raise ValueError("Apple 查询接口 trackViewUrl 应为字符串")
    return VersionInfo(
        name=name,
        version=version,
        url=url,
    )

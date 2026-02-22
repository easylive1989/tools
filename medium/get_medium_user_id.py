#!/usr/bin/env python3
"""
取得 Medium User ID
"""

import os
import requests


def get_medium_user_id():
    token = os.environ.get('MEDIUM_TOKEN')

    if not token:
        print("請設定環境變數 MEDIUM_TOKEN")
        return None

    response = requests.get(
        "https://api.medium.com/v1/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    if response.status_code == 200:
        data = response.json()
        return data['data']['id']
    else:
        print(f"API 錯誤：{response.status_code}")
        return None


if __name__ == "__main__":
    user_id = get_medium_user_id()
    if user_id:
        print(user_id)
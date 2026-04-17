import json
import requests

# https://developers.notion.com/reference/intro
class NotionApi:
    def __init__(self, token):
        self.token = token

    def query_database(self, database_id: str, body: dict):
        return requests.post(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            data = json.dumps(body),
            headers = self.__header()
        )

    def patch_page(self, page_id: str, properties: dict):
        requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            data = json.dumps(properties),
            headers = self.__header()
        )

    def create_page(self, database_id: str, properties: dict):
        body = {
            "parent": { "database_id": database_id },
            "properties": properties
        }

        return requests.post(
            "https://api.notion.com/v1/pages",
            data = json.dumps(body),
            headers = self.__header()
        )

    def get_page(self, page_id: str):
        """獲取頁面屬性和基本資訊"""
        return requests.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=self.__header()
        )

    def get_block_children(self, block_id: str):
        """獲取區塊的子內容"""
        return requests.get(
            f"https://api.notion.com/v1/blocks/{block_id}/children",
            headers=self.__header()
        )

    def get_page_content(self, page_id: str):
        """獲取完整的頁面內容，包含屬性和所有區塊"""
        page_response = self.get_page(page_id)
        blocks_response = self.get_block_children(page_id)

        if page_response.status_code != 200:
            raise Exception(f"無法獲取頁面: {page_response.text}")

        if blocks_response.status_code != 200:
            raise Exception(f"無法獲取頁面內容: {blocks_response.text}")

        return {
            "page": page_response.json(),
            "blocks": blocks_response.json()
        }

    def get_database(self, database_id: str):
        """獲取資料庫屬性結構"""
        return requests.get(
            f"https://api.notion.com/v1/databases/{database_id}",
            headers=self.__header()
        )

    def get_property_names_by_type(self, database_id: str, property_types: list):
        """根據屬性類型自動偵測屬性名稱"""
        response = self.get_database(database_id)
        if response.status_code != 200:
            raise Exception(f"無法獲取資料庫 {database_id}: {response.text}")

        properties = response.json()["properties"]
        result = {}

        for prop_name, prop_info in properties.items():
            prop_type = prop_info['type']
            if prop_type in property_types:
                result[prop_type] = prop_name

        return result

    def append_block_children(self, block_id: str, children: list):
        """向頁面或區塊加入子區塊內容"""
        body = {
            "children": children
        }

        return requests.patch(
            f"https://api.notion.com/v1/blocks/{block_id}/children",
            data=json.dumps(body),
            headers=self.__header()
        )

    def check_record_exists(self, database_id: str, title_property: str, title_value: str):
        """檢查資料庫中是否已存在指定標題的記錄"""
        filter_body = {
            "filter": {
                "property": title_property,
                "title": {
                    "equals": title_value
                }
            }
        }

        response = self.query_database(database_id, filter_body)
        if response.status_code == 200:
            results = response.json()["results"]
            return len(results) > 0
        else:
            print(f"檢查記錄存在失敗: {response.status_code}")
            print(response.text)
            return False

    def __header(self) -> dict:
        return {
            "Content-type": "application/json",
            "Notion-Version": "2022-06-28",
            "Authorization": f"Bearer {self.token}"
        }

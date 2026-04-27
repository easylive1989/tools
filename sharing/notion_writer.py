import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, ".."))
sys.path.insert(0, _here)

from common.notion import NotionApi
from extractor import ExtractResult

DB_ID = "974f5e43cac84f818fe23f35e463286b"


def build_properties(result: ExtractResult) -> dict:
    props: dict = {}
    props["Name"] = {"title": [{"text": {"content": result.name}}]}
    if result.url:
        props["連結"] = {"url": result.url}
    if result.region:
        props["地區"] = {"select": {"name": result.region}}
    if result.town:
        props["鄉鎮"] = {"select": {"name": result.town}}
    props["類型"] = {"multi_select": [{"name": t} for t in result.types]}
    note = result.note[:2000]
    props["Note"] = {"rich_text": [{"text": {"content": note}}]}
    if result.rating is not None:
        props["評級"] = {"number": result.rating}
    return props


def write(result: ExtractResult, notion: NotionApi) -> None:
    properties = build_properties(result)
    resp = notion.create_page(DB_ID, properties)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Notion API error {resp.status_code}: {resp.text[:200]}")

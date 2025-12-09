# backend/app/notion/client.py

"""
Notion API との通信を担当するクライアントモジュール。
"""

from typing import Any, Dict, List

import httpx

from .config import get_notion_config


class NotionClientError(RuntimeError):
    """Notion クライアント全般の例外。"""


class NotionAuthError(NotionClientError):
    """認証・権限関連のエラー。"""


class NotionAPIError(NotionClientError):
    """その他 Notion API 呼び出し時のエラー。"""


class NotionClient:
    """
    Notion API の薄いラッパークライアント。

    - データベースの query
    - ページの更新（将来用の下地）
    """

    def __init__(self, timeout: float = 10.0) -> None:
        self.config = get_notion_config()
        self._timeout = timeout

    def _build_headers(self) -> Dict[str, str]:
        """
        Notion API 呼び出しに必要なヘッダーを構築。
        """
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Notion-Version": self.config.api_version,
            "Content-Type": "application/json",
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        """
        HTTP レスポンスコードに応じて適切な例外を投げる。
        """
        if response.status_code == 401:
            raise NotionAuthError("Unauthorized. Check NOTION_API_KEY.")
        if response.status_code == 403:
            raise NotionAuthError("Forbidden. Check Notion integration permissions.")
        if response.status_code >= 400:
            raise NotionAPIError(
                f"Notion API error: {response.status_code} {response.text}"
            )

    def query_unprocessed_entries(self) -> List[Dict[str, Any]]:
        """
        Status が『未処理』のレコードを Notion データベースから取得する。

        返り値は Notion API の生のページオブジェクトのリスト。
        上位レイヤー（service.py）で内部モデルに変換する。
        """
        url = f"{self.config.api_base_url}/databases/{self.config.database_id}/query"

        # docs/09_notion_schema.md に従い、Status == '未処理' をフィルタ。
        payload: Dict[str, Any] = {
            "filter": {
                "property": "Status",
                "select": {"equals": "未処理"},
            }
        }

        try:
            response = httpx.post(
                url,
                headers=self._build_headers(),
                json=payload,
                timeout=self._timeout,
            )
        except httpx.RequestError as exc:
            raise NotionClientError(f"Failed to call Notion API: {exc}") from exc

        self._raise_for_status(response)

        data = response.json()
        results = data.get("results", [])
        if not isinstance(results, list):
            raise NotionAPIError("Unexpected Notion API response format: 'results' is not a list.")

        return results

    def update_page_properties(self, page_id: str, properties: Dict[str, Any]) -> None:
        """
        ページのプロパティを更新する。

        Phase1 では主に「インターフェースの用意」のみ。
        実際のアップデートは Phase2 以降の要件に応じて拡張する。
        """
        url = f"{self.config.api_base_url}/pages/{page_id}"

        body = {"properties": properties}

        try:
            response = httpx.patch(
                url,
                headers=self._build_headers(),
                json=body,
                timeout=self._timeout,
            )
        except httpx.RequestError as exc:
            raise NotionClientError(f"Failed to update Notion page: {exc}") from exc

        self._raise_for_status(response)


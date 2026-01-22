from typing import Any, Dict

import httpx

from .config import OctoBotSettings, get_octobot_settings


class OctoBotClientError(Exception):
    """OctoBot クライアント全般の基底例外。"""


class OctoBotHTTPError(OctoBotClientError):
    """HTTP ステータスコードがエラーだった場合の例外。"""

    def __init__(self, status_code: int, body: Any | None = None) -> None:
        super().__init__(f"OctoBot API error: status_code={status_code}")
        self.status_code = status_code
        self.body = body


class OctoBotConnectionError(OctoBotClientError):
    """接続エラー・タイムアウト時の例外。"""


class OctoBotClient:
    """
    OctoBot 外部シグナル API への HTTP クライアント。

    NOTE:
      - 実際にどのパスへ POST するかは base_url の設計次第。
        ここでは base_url に「シグナル送信エンドポイントのフル URL」が入っている想定。
    """

    def __init__(self, settings: OctoBotSettings | None = None) -> None:
        self._settings = settings or get_octobot_settings()

    @property
    def base_url(self) -> str:
        return self._settings.base_url

    @property
    def timeout(self) -> int:
        return self._settings.timeout_seconds

    @property
    def api_key(self) -> str:
        return self._settings.api_key

    def _build_headers(self) -> Dict[str, str]:
        """
        OctoBot API 呼び出しに使用する HTTP ヘッダを構築する。
        """
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def send_signal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        シグナル 1件分を OctoBot 外部 API に送信する。

        :param payload: {action, confidence, reason, timestamp} を含む辞書。
        :raises OctoBotHTTPError: OctoBot が 4xx/5xx を返した場合。
        :raises OctoBotConnectionError: 接続エラーやタイムアウト時。
        :return: OctoBot からの JSON レスポンス（成功時）。
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.base_url,
                    json=payload,
                    headers=self._build_headers(),
                )
        except httpx.RequestError as exc:  # 接続エラー・タイムアウトなど
            raise OctoBotConnectionError(str(exc)) from exc

        if response.status_code // 100 != 2:
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise OctoBotHTTPError(status_code=response.status_code, body=body)

        try:
            return response.json()
        except ValueError:
            # JSON でないレスポンスはそのままテキストで返す。
            return {"raw": response.text}

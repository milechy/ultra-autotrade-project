from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, conint

from app.ai.schemas import TradeAction


class OctoBotSignal(BaseModel):
    """
    AIAnalysisResult 1件分をベースにした、/octobot/signal 用の入力モデル。
    """
    id: str = Field(..., description="Notion レコード ID など、シグナルの一意な識別子")
    url: Optional[str] = Field(
        None,
        description="ニュース記事の URL。ログやデバッグ用の補足情報",
    )
    action: TradeAction = Field(
        ...,
        description="AI が判定したアクション（BUY / SELL / HOLD）",
    )
    confidence: conint(ge=0, le=100) = Field(
        ...,
        description="信頼度スコア（0〜100）",
    )
    reason: str = Field(
        ...,
        description="なぜその action になったかの要約テキスト",
    )
    timestamp: datetime = Field(
        ...,
        description="AI が判定した時刻（ISO8601, UTC 推奨）",
    )


class OctoBotSignalRequest(BaseModel):
    """
    /octobot/signal のリクエストボディ。

    AIAnalysisResult 相当のシグナルを複数件まとめて送信できる。
    """
    signals: List[OctoBotSignal] = Field(
        ...,
        description="送信対象とするシグナルの配列",
    )
    count: int = Field(
        ...,
        ge=0,
        description="signals 配列の件数（サーバ側で整合チェックに利用）",
    )

    def validate_count(self) -> None:
        """
        count と signals の長さに差異がある場合に ValueError を投げる簡易チェック。

        FastAPI レイヤで 400 等にマッピングする想定。
        """
        if self.count != len(self.signals):
            raise ValueError(
                f"count ({self.count}) does not match number of signals ({len(self.signals)})."
            )


class OctoBotSignalStatus(str, Enum):
    SENT = "sent"
    SKIPPED = "skipped"
    FAILED = "failed"


class OctoBotSignalDetail(BaseModel):
    """
    シグナルごとの送信結果詳細。
    """
    id: str = Field(..., description="対象となったシグナルの ID")
    status: OctoBotSignalStatus = Field(
        ...,
        description="sent / skipped / failed",
    )
    message: Optional[str] = Field(
        None,
        description="エラー内容やスキップ理由などの補足メッセージ（正常時は None 推奨）",
    )


class OctoBotSignalResponse(BaseModel):
    """
    /octobot/signal のレスポンスボディ。

    集計サマリ＋各シグナルの結果詳細を返す。
    """
    success_count: int = Field(..., ge=0, description="送信に成功したシグナル件数")
    skipped_count: int = Field(..., ge=0, description="安全弁によりスキップしたシグナル件数")
    failed_count: int = Field(..., ge=0, description="送信に失敗したシグナル件数")
    details: List[OctoBotSignalDetail] = Field(
        ...,
        description="各シグナルごとの処理結果の詳細",
    )

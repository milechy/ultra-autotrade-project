from datetime import timedelta
from typing import List, Tuple

from .client import OctoBotClient, OctoBotClientError
from .schemas import (
    OctoBotSignal,
    OctoBotSignalDetail,
    OctoBotSignalRequest,
    OctoBotSignalResponse,
    OctoBotSignalStatus,
)


class OctoBotService:
    """
    AIAnalysisResult 相当の入力から、OctoBot 外部 API 向けシグナルを生成・送信するサービス層。

    - 信頼度しきい値
    - 連続トレード制限（過剰取引防止）

    などの「安全弁ロジック」を適用する責務を担う。
    """

    def __init__(
        self,
        client: OctoBotClient | None = None,
        min_confidence: int = 0,
        max_same_action_per_hour: int = 3,
    ) -> None:
        """
        :param client: OctoBotClient。None の場合はデフォルト設定で生成。
        :param min_confidence: この値未満のシグナルは「skipped」として扱う。
        :param max_same_action_per_hour:
            1時間以内に同一アクションを許可する最大回数。
            超過分は過剰取引とみなして「skipped」とする。
        """
        self._client = client or OctoBotClient()
        self._min_confidence = min_confidence
        self._max_same_action_per_hour = max_same_action_per_hour

        # 直近1時間のシグナル履歴 (action, timestamp)
        # - action: "BUY" / "SELL" / "HOLD" など
        # - timestamp: datetime
        self._recent_actions: List[Tuple[str, object]] = []

    def process_signals(self, request: OctoBotSignalRequest) -> OctoBotSignalResponse:
        """
        /octobot/signal のメイン処理。

        - リクエストの整合性チェック
        - 安全弁ロジックによる「送信/スキップ」の判定
        - OctoBot 外部 API への送信
        - 結果の集計
        """
        # count と signals 長さの整合性チェック（400 用）
        request.validate_count()

        details: List[OctoBotSignalDetail] = []

        success_count = 0
        skipped_count = 0
        failed_count = 0

        for signal in request.signals:
            # 1. 安全弁：信頼度しきい値チェック
            if signal.confidence < self._min_confidence:
                details.append(
                    OctoBotSignalDetail(
                        id=signal.id,
                        status=OctoBotSignalStatus.SKIPPED,
                        message=(
                            f"confidence {signal.confidence} "
                            f"< min_confidence {self._min_confidence}"
                        ),
                    )
                )
                skipped_count += 1
                continue

            # 2. 連続トレード制限チェック（1時間以内の同一アクション回数）
            if self._should_skip_by_rate_limit(signal):
                details.append(
                    OctoBotSignalDetail(
                        id=signal.id,
                        status=OctoBotSignalStatus.SKIPPED,
                        message="skipped by trade rate limiting rule",
                    )
                )
                skipped_count += 1
                continue

            # 3. OctoBot 外部 API へ送信
            try:
                self._send_to_octobot(signal)
            except OctoBotClientError as exc:
                failed_count += 1
                details.append(
                    OctoBotSignalDetail(
                        id=signal.id,
                        status=OctoBotSignalStatus.FAILED,
                        message=str(exc),
                    )
                )
                continue

            # 成功
            success_count += 1
            details.append(
                OctoBotSignalDetail(
                    id=signal.id,
                    status=OctoBotSignalStatus.SENT,
                    message=None,
                )
            )

        return OctoBotSignalResponse(
            success_count=success_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            details=details,
        )

    # --- 内部メソッド ---

    def _should_skip_by_rate_limit(self, signal: OctoBotSignal) -> bool:
        """
        過剰取引・連続トレード制限に基づいてシグナルをスキップするか判断する。

        ルール（08_automation_rules.md より簡易実装）:
          - 1時間以内に同一アクションが一定回数（max_same_action_per_hour）を超える場合は SKIPPED。

        NOTE:
          - ここではプロセス内メモリでの簡易カウントのみ。
          - 本番運用では Redis などを使った分散レート制限に置き換えを検討。
        """
        # TradeAction Enum / str 両対応で action 値を取得
        action_val = (
            signal.action.value if hasattr(signal.action, "value") else str(signal.action)
        )

        # 直近1時間の履歴だけを残す
        window_start = signal.timestamp - timedelta(hours=1)
        self._recent_actions = [
            (a, ts) for (a, ts) in self._recent_actions if ts >= window_start
        ]

        # 同一アクションの件数をカウント
        same_action_count = sum(1 for (a, _) in self._recent_actions if a == action_val)

        # 既にしきい値以上なら、今回のシグナルはスキップ
        if same_action_count >= self._max_same_action_per_hour:
            return True

        # 送信許可する場合のみ、履歴に追加
        self._recent_actions.append((action_val, signal.timestamp))
        return False

    def _send_to_octobot(self, signal: OctoBotSignal) -> None:
        """
        OctoBot 外部 API へシグナルを送信する。

        実際に送るのは docs/06_octobot_signal_flow.md で定義された
        { action, confidence, reason, timestamp } のみ。
        """
        # TradeAction が Enum の場合と素の str の場合両方に対応
        action_val = (
            signal.action.value if hasattr(signal.action, "value") else str(signal.action)
        )

        payload = {
            "action": action_val,
            "confidence": signal.confidence,
            "reason": signal.reason,
            "timestamp": signal.timestamp.isoformat(),
        }
        self._client.send_signal(payload)

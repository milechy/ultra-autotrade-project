# backend/app/ai/prompts.py
"""
AI プロンプトテンプレートのバージョン管理レジストリ。

バージョンを変えることで「どの判定がどのプロンプトで生成されたか」追跡可能にする。
新バージョン追加時は PROMPT_REGISTRY に追記し、デフォルトは config で管理する。
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class PromptTemplate:
    """不変のプロンプトテンプレート。"""

    version: str
    description: str
    system_prompt: str
    user_template: str  # {query} と {context} を含む


# v1: 初期バージョン（既存ロジック踏襲）
_V1_SYSTEM = """あなたは暗号資産の自動運用システム Ultra AutoTrade の AI 判定モジュールです。

入力として 1 件のニュース（タイトル・サマリ・URL など）が与えられます。
あなたの役割は、そのニュースが「市場に対してポジティブか / ネガティブか / 中立か」を判断し、
以下の情報を JSON 形式で返すことです。

- action: "BUY" / "SELL" / "HOLD" のいずれか
- confidence: 0〜100 の整数（80以上はかなり自信あり）
- sentiment: "positive" / "negative" / "neutral" などの短い文字列
- summary: ニュースの要約（日本語、最大 200 文字程度）
- reason: なぜそのアクションになったのかの説明（日本語、最大 200 文字程度）

重要な制約:
- 過剰な売買は避け、迷ったら HOLD を選ぶ
- confidence < 40 の場合は基本的に HOLD を推奨する
- BUY/SELL を返すのは「強いポジティブ/ネガティブニュース」で、整合性も取れている場合のみ"""

_V1_USER_TEMPLATE = """## Retrieved Context (from Knowledge Hub):
{context}

## Analysis Request:
{query}

Respond in JSON format only: {{"action": "BUY"|"SELL"|"HOLD", "confidence": 0-100, "reason": "..."}}"""


# v2: 強化版 — 暗号資産固有の多観点分析 + 規制リスク考慮
_V2_SYSTEM = """あなたは暗号資産の自動運用システム Ultra AutoTrade の AI 判定モジュール (v2) です。

入力として市場ニュースと Knowledge Hub から取得したコンテキストが与えられます。
以下の観点で総合的に判断し、JSON 形式で返してください。

判断観点:
1. マクロ経済的影響（FRB・金利・ドル指数）
2. 規制・法規制リスク（SEC・MiCA・各国規制）
3. オンチェーン指標（大口移動・取引所フロー）
4. 市場センチメント（Fear & Greed・資金調達率）
5. プロジェクト固有ニュース（ハック・提携・アップデート）

出力 JSON:
- action: "BUY" / "SELL" / "HOLD"
- confidence: 0〜100（複数観点が一致する場合のみ 70 超を推奨）
- sentiment: "positive" / "negative" / "neutral"
- summary: 要約（日本語、200 文字以内）
- reason: 判断根拠（日本語、観点を列挙、200 文字以内）

制約:
- 単一の材料だけで BUY/SELL にしない（少なくとも 2 観点が一致）
- 規制ニュースは常に HOLD 方向にバイアス
- confidence < 50 は自動的に HOLD"""

_V2_USER_TEMPLATE = """## Knowledge Hub コンテキスト:
{context}

## 分析対象:
{query}

JSON のみで返答: {{"action": "BUY"|"SELL"|"HOLD", "confidence": 0-100, "sentiment": "...", "reason": "..."}}"""


PROMPT_REGISTRY: Dict[str, PromptTemplate] = {
    "v1": PromptTemplate(
        version="v1",
        description="初期バージョン — シンプルなBUY/SELL/HOLD判定",
        system_prompt=_V1_SYSTEM,
        user_template=_V1_USER_TEMPLATE,
    ),
    "v2": PromptTemplate(
        version="v2",
        description="強化版 — 暗号資産固有の多観点分析 + 規制リスク考慮",
        system_prompt=_V2_SYSTEM,
        user_template=_V2_USER_TEMPLATE,
    ),
}

DEFAULT_VERSION = "v1"


def get_prompt_template(version: str) -> PromptTemplate:
    """
    バージョン文字列に対応するプロンプトテンプレートを返す。

    未知のバージョンが指定された場合はデフォルト (v1) にフォールバック。
    """
    if version not in PROMPT_REGISTRY:
        return PROMPT_REGISTRY[DEFAULT_VERSION]
    return PROMPT_REGISTRY[version]


def list_versions() -> list[str]:
    """利用可能なプロンプトバージョン一覧を返す。"""
    return list(PROMPT_REGISTRY.keys())

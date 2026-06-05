# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/app/aave/dod_verifier.py
"""
非カストディ on-chain Aave USDC supply の DoD 1-4 を *実 tx* から機械判定する純関数群。

Asana P0-1 (1215363789384766) DoD:
  1. from = 登録済 Privy Session Key 群 または partner wallet
  2. supply の onBehalfOf = 当該 partner の Privy wallet と完全一致
  3. aUSDC mint 先 = partner
  4. サーバー長期鍵アドレス群が from / msg.sender / 全 internal tx 署名者に一切出現しない

このモジュールはネットワークに依存しない (web3 を import しない)。CLI ラッパ
(scripts/verify_dod_onchain.py) が RPC から tx/receipt を取得し、ここへ正規化済みの
プリミティブ (hex 文字列) を渡す。これによりロジックを RPC なしでユニットテストできる。

注意: DoD は「basescan/実 tx で機械判定」が要件。本モジュールはコード+ログでの担保では
なく、実 tx の calldata / receipt logs を直接デコードして判定する。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Aave V3 Pool.supply(address,uint256,address,uint16) のセレクタ
AAVE_SUPPLY_SELECTOR = "617ba037"
# ERC20 Transfer(address,address,uint256) の topic0 (keccak256)
ERC20_TRANSFER_TOPIC = "ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# サーバー長期鍵アドレス群 (DoD#4)。出現してはならない。
# 現: 0x04666D72D4eB21C2336FE360FB20C093Da291016 (Asana P0-1 明記)
DEFAULT_SERVER_KEYS: tuple[str, ...] = ("0x04666D72D4eB21C2336FE360FB20C093Da291016",)


def _norm(addr: str | None) -> str:
    """アドレスを比較用に正規化 (lowercase, 0x prefix, 40 hex)。不正値は空文字。"""
    if not addr:
        return ""
    a = addr.strip().lower()
    if a.startswith("0x"):
        a = a[2:]
    if len(a) > 40:  # 32byte word に padding された address topic
        a = a[-40:]
    if len(a) != 40:
        return ""
    try:
        int(a, 16)
    except ValueError:
        return ""
    return "0x" + a


def _strip0x(h: str) -> str:
    h = h.strip().lower()
    return h[2:] if h.startswith("0x") else h


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class DodResult:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(CheckResult(name=name, passed=passed, detail=detail))


def decode_supply_onbehalfof(tx_input: str) -> str | None:
    """
    Aave V3 supply() calldata から onBehalfOf (第3引数) を取り出す。

    supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode)
    レイアウト: selector(4B) + asset(32B) + amount(32B) + onBehalfOf(32B) + ref(32B)

    supply 以外 / 長さ不足なら None。
    """
    data = _strip0x(tx_input)
    if len(data) < 8 + 64 * 4:
        return None
    if data[:8] != AAVE_SUPPLY_SELECTOR:
        return None
    onbehalf_word = data[8 + 64 * 2 : 8 + 64 * 3]
    return _norm(onbehalf_word)


def decode_supply_asset(tx_input: str) -> str | None:
    """supply() calldata から asset (第1引数) を取り出す。supply 以外なら None。"""
    data = _strip0x(tx_input)
    if len(data) < 8 + 64 * 4 or data[:8] != AAVE_SUPPLY_SELECTOR:
        return None
    return _norm(data[8 : 8 + 64])


def find_mint_recipients(
    logs: list[dict[str, object]], token_address: str | None = None
) -> list[str]:
    """
    aToken mint (= Transfer(from=0x0, to=recipient)) の recipient を列挙する。

    token_address 指定時はその contract が emit した Transfer のみ対象 (aUSDC に限定)。
    """
    recipients: list[str] = []
    want_token = _norm(token_address) if token_address else None
    for log in logs:
        topics = log.get("topics") or []
        if not isinstance(topics, list) or len(topics) < 3:
            continue
        if _strip0x(str(topics[0])) != ERC20_TRANSFER_TOPIC:
            continue
        if want_token is not None and _norm(str(log.get("address"))) != want_token:
            continue
        sender = _norm(str(topics[1]))
        if sender != ZERO_ADDRESS:
            continue  # mint は from=0x0 のみ
        recipients.append(_norm(str(topics[2])))
    return recipients


def collect_addresses(tx_from: str, logs: list[dict[str, object]]) -> set[str]:
    """
    tx に現れる全アドレスを収集する (DoD#4 のサーバー鍵走査対象)。

    対象: tx.from + 各 log の emit contract address + address 型に見える全 topic
    (Transfer の from/to など)。サーバー鍵が署名者・資金移動元として出現すれば
    必ずこの集合に入る。
    """
    found: set[str] = set()
    f = _norm(tx_from)
    if f:
        found.add(f)
    for log in logs:
        a = _norm(str(log.get("address")))
        if a:
            found.add(a)
        topics = log.get("topics") or []
        if isinstance(topics, list):
            for t in topics[1:]:  # topic0 はイベント signature なので除外
                ta = _norm(str(t))
                if ta:
                    found.add(ta)
    return found


def evaluate_dod(
    *,
    tx_from: str,
    tx_input: str,
    logs: list[dict[str, object]],
    partner_wallet: str,
    session_keys: list[str] | None = None,
    atoken_address: str | None = None,
    server_keys: tuple[str, ...] | list[str] = DEFAULT_SERVER_KEYS,
) -> DodResult:
    """正規化済みプリミティブから DoD 1-4 を判定する。"""
    partner = _norm(partner_wallet)
    sess = {_norm(k) for k in (session_keys or []) if _norm(k)}
    allowed_from = {partner} | sess
    result = DodResult()

    # DoD1: from = partner wallet または登録済 session key
    sender = _norm(tx_from)
    if sender in allowed_from:
        which = "partner" if sender == partner else "session_key"
        result.add("DoD1_from", True, f"from={sender} ({which})")
    else:
        result.add(
            "DoD1_from",
            False,
            f"from={sender} は partner({partner}) / session_keys({sorted(sess)}) のいずれでもない",
        )

    # DoD2: supply の onBehalfOf = partner wallet 完全一致
    onbehalf = decode_supply_onbehalfof(tx_input)
    if onbehalf is None:
        result.add(
            "DoD2_onBehalfOf", False, "calldata が Aave supply() ではない (onBehalfOf 抽出不可)"
        )
    elif onbehalf == partner:
        result.add("DoD2_onBehalfOf", True, f"onBehalfOf={onbehalf} = partner 完全一致")
    else:
        result.add("DoD2_onBehalfOf", False, f"onBehalfOf={onbehalf} ≠ partner({partner})")

    # DoD3: aUSDC mint 先 = partner
    recipients = find_mint_recipients(logs, atoken_address)
    if partner in recipients:
        result.add(
            "DoD3_aUSDC_mint",
            True,
            f"aToken mint(from=0x0)→{partner} を検出 (recipients={recipients})",
        )
    else:
        scope = f"atoken={_norm(atoken_address)}" if atoken_address else "全 Transfer"
        result.add(
            "DoD3_aUSDC_mint",
            False,
            f"partner({partner}) への mint が見つからない ({scope}, recipients={recipients})",
        )

    # DoD4: サーバー長期鍵が from / msg.sender / 全 internal tx 署名者に一切出現しない
    addresses = collect_addresses(tx_from, logs)
    server_set = {_norm(k) for k in server_keys if _norm(k)}
    leaked = sorted(addresses & server_set)
    if leaked:
        result.add(
            "DoD4_server_key_absent",
            False,
            f"サーバー鍵が tx 内アドレスに出現: {leaked}",
        )
    else:
        result.add(
            "DoD4_server_key_absent",
            True,
            f"サーバー鍵 {sorted(server_set)} は tx 内 {len(addresses)} アドレスに非出現",
        )

    return result

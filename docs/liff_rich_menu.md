# LINE リッチメニュー設定手順

## 概要
Ultra AutoTradeのLINEリッチメニューを設定する手順です。

## 前提条件
- LINE Official Account作成済み
- LIFF App作成済み (LIFF ID取得済み)

## リッチメニュー構成 (2列 × 1行)

| ボタン | ラベル | アクション |
|--------|--------|----------|
| 左 | 📊 AI判定を見る | LIFFを開く: /liff/feed |
| 右 | ✅ 承認する | LIFFを開く: /liff/approve |

## 設定手順

1. LINE Developers Console → Messaging API → リッチメニュー
2. 「作成」→ サイズ: 2580×1686
3. エリア分割: 2列
4. 左エリア: タイプ=URI, URI=line://app/{LIFF_ID}?path=/liff/feed
5. 右エリア: タイプ=URI, URI=line://app/{LIFF_ID}?path=/liff/approve
6. 「保存して適用」

## 環境変数

```
NEXT_PUBLIC_LIFF_ID=your_liff_id_here
```

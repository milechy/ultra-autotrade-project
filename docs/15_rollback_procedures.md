# 15_rollback_procedures.md  
Ultra AutoTrade – ロールバック手順

---

# 1. ロールバックの目的
誤作動・暴落・通信障害などで  
資金損失を防ぐための“即時復旧”手順。

---

# 2. 取引ステップ別ロールバック

## 2.1 Notion → AI
失敗時は Notion の該当ブロックを “再処理キュー” に移動。

## 2.2 AI → OctoBot
OctoBot API失敗時：

- 3回リトライ  
- 失敗時は “HOLD 判定” 処理に切り替え  
- 同時に手動確認通知

## 2.3 OctoBot → Aave
Aave deposit 失敗時：

- ガスリトライ  
- ガス高騰時は自動キャンセル  
- 失敗ログを Notion に保存  

withdraw 失敗時：

- Gas不足でない場合は即緊急通知

## 2.4 Aave 操作失敗時（/aave/rebalance）

### 失敗パターン
- Aave クライアントエラー（RPC 断、レスポンス異常）
- ヘルスファクター取得失敗
- 想定外の例外

### Phase4 実装での挙動
- deposit / withdraw 前にヘルスファクター取得を試みる（失敗時は None として継続）
- `BUY/SELL/HOLD` → `DEPOSIT/WITHDRAW/NOOP` 判定後、
  - クライアント例外が発生した場合は
    - 実際のトランザクションは送られない
    - `status="error"`, `amount=0` として API レスポンスを返す
- いかなるエラー時も **「ポジションを増やす方向の変更は行わない」** ことを保証する

### 運用側でのロールバック対応
- Aave 関連でエラーが連続した場合：
  - OctoBot シグナル → Aave 連携を一時停止
  - 必要に応じて手動で Aave ダッシュボードから withdraw
  - 緊急停止条件（ヘルスファクター < 1.6 など）に該当する場合は「全停止＋通知」を優先

---

# 3. 本番環境のロールバック

## Aave 運用ロールバック

1. 自動運用停止  
2. 資金をステーブルコインに変換  
3. ウォレットへ退避  
4. LINE/Slack通知

---

# 4. バージョン管理ロールバック
GitHub：

- `main` のタグ管理  
- `rollback/vX.Y.Z` ブランチの作成  
- 前バージョンをデプロイ可能

---

# 5. 緊急停止（Emergency Mode）

### 発火条件例
- 価格変動 > 20%  
- ヘルスファクター < 1.6  
- OctoBot応答なし  
- AI API失敗率 > 20%  

### 発動後
- 全処理停止  
- Aave withdraw  
- 通知

---

# 4. staging 環境でのロールバック手順（インフラ視点）

本章では、Phase7 で整備した staging 環境において、  
デプロイ後に問題が発生した場合のロールバック手順を整理する。

基本方針：

- staging では、**アプリケーションコードのバージョンを元に戻す** ことでロールバックする。
- `.env.staging` は原則としてそのまま（接続先・キーは変えない）。
- 緊急停止フラグを併用し、問題の波及を防ぐ。

## 4.1 Docker + docker-compose パターン

staging で Docker を利用している場合（`docker-compose.staging.yml`）の手順。

### 4.1.1 直前デプロイの確認

1. サーバにログイン（例：`ssh ultra@staging-server`）
2. プロジェクトルートへ移動：
   ```bash
   cd /opt/ultra-autotrade

3. 現在の Git 状態を確認：
git log -5 --oneline


### 4.1.2 1 つ前のコミットに戻す
1. 直前のコミット ID を確認し、その 1 つ前のコミットを特定する。
2. staging 用ブランチ（例：staging）をそのコミットにリセット：

git checkout staging
git reset --hard <rollback_target_commit>

3. デプロイスクリプトを実行：

./scripts/deploy_staging_backend.sh

### 4.1.3 動作確認
1. コンテナの状態：

docker compose -f docker-compose.staging.yml ps

2. ヘルスチェック：
curl -fsS http://localhost:8000/health

3. 必要に応じて、staging 用のテストケース（Notion 連携 / OctoBot / Aave テストネット）を手動確認する。
問題が解消された場合、緊急停止フラグの解除を検討する（詳細は 19_operations_runbook.md を参照）。

### 4.2 systemd パターン
Docker を利用せず、systemd + uvicorn で常駐させている場合。

### 4.2.1 アプリケーションのロールバック
1. サーバにログインし、アプリケーションディレクトリへ移動：
cd /opt/ultra-autotrade

2. Git でロールバック対象コミットへ戻す：
git checkout staging
git reset --hard <rollback_target_commit>

3. 必要であれば依存パッケージを再インストール：
source venv/bin/activate
pip install -r backend/requirements.txt

### 4.2.2 サービス再起動
sudo systemctl restart ultra-autotrade-backend
sudo systemctl status ultra-autotrade-backend

その後、/health やログで状態を確認する。

### 4.3 緊急停止フラグとの組み合わせ
重大な障害が発生した場合は、ロールバック作業に入る前に 緊急停止フラグを ON にする ことを推奨する。
1. 緊急停止フラグを ON（具体的な操作方法は 19_operations_runbook.md 参照）
2. 上記 4.1 / 4.2 の手順でロールバックを実施
3. ロールバック後、以下を確認：
 - /health が OK を返す
 - 主要なユースケース（Notion → AI → OctoBot → Aave） が staging で正常に動作する
4. 問題が解消されたと判断したら、緊急停止フラグを OFF にする

### 4.4 ロールバックの記録
ロールバックを実施した場合、以下を記録しておくことが望ましい。
- 実施日時
- 対象環境（staging / production）
- ロールバックしたコミット ID / バージョン
- ロールバックの理由（障害概要）
- 影響範囲と対策メモ

これらは、今後のリリース計画や回帰テストの観点で重要な情報となる。
# backend/app/knowledge/__init__.py

"""
Knowledge Hub モジュール。

URL またはテキストを取り込み、チャンク分割・埋め込み生成を行い
PostgreSQL + pgvector でベクトル検索可能にする RAG 基盤を提供する。

主な責務:
- URL スクレイピングまたは生テキストの受け付け
- テキストのチャンク分割（~500 トークン / 50 オーバーラップ）
- OpenAI text-embedding-3-small による埋め込み生成
- pgvector を利用したコサイン類似度ベクトル検索
"""

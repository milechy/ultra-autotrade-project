// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
export type AiDecision = {
  id: string;
  timestamp: string;
  query: string;
  final_action: "BUY" | "SELL" | "HOLD";
  final_confidence: number;
  claude_action: "BUY" | "SELL" | "HOLD";
  claude_confidence: number;
  claude_reason: string;
  claude_raw_response?: string;
  gpt4o_action?: "BUY" | "SELL" | "HOLD";
  gpt4o_confidence?: number;
  gpt4o_reason?: string;
  gpt4o_raw_response?: string;
  agreed: boolean;
  rag_context?: { chunks: string[]; query: string; source_count: number };
  executed: boolean;
};

export const MOCK_DECISIONS: AiDecision[] = [
  {
    id: "d001",
    timestamp: new Date(Date.now() - 1000 * 60 * 10).toISOString(),
    query: "BTC/USDT の現在のトレンドを分析してください。RSI=62, MACD上昇中",
    final_action: "BUY",
    final_confidence: 0.87,
    claude_action: "BUY",
    claude_confidence: 0.87,
    claude_reason: "RSIが中立域で上昇トレンド継続。MACDのゴールデンクロス確認。強気継続と判断。",
    claude_raw_response: '{"action":"BUY","confidence":0.87,"reason":"RSIが中立域で上昇トレンド継続..."}',
    gpt4o_action: "BUY",
    gpt4o_confidence: 0.82,
    gpt4o_reason: "テクニカル指標が強気を示している。トレンド継続の可能性が高い。",
    gpt4o_raw_response: '{"action":"BUY","confidence":0.82,"reason":"テクニカル指標が強気..."}',
    agreed: true,
    rag_context: {
      query: "BTC/USDT トレンド分析",
      chunks: ["2026年3月のBTC市場は強気相場が継続...", "機関投資家のBTC購入が加速している..."],
      source_count: 2,
    },
    executed: true,
  },
  {
    id: "d002",
    timestamp: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
    query: "ETH/USDT: Health Factor 1.63, 流動性低下の懸念あり",
    final_action: "HOLD",
    final_confidence: 0.72,
    claude_action: "HOLD",
    claude_confidence: 0.72,
    claude_reason: "Health Factor が閾値1.6に近接。安全マージンが小さいため様子見を推奨。",
    claude_raw_response: '{"action":"HOLD","confidence":0.72,"reason":"Health Factor が閾値..."}',
    agreed: true,
    rag_context: {
      query: "ETH Aave Health Factor リスク",
      chunks: ["Health Factor 1.6以下はリスク領域..."],
      source_count: 1,
    },
    executed: false,
  },
  {
    id: "d003",
    timestamp: new Date(Date.now() - 1000 * 60 * 90).toISOString(),
    query: "BTC/USDT: 急激な価格上昇後の調整局面か？ RSI=78",
    final_action: "HOLD",
    final_confidence: 0.61,
    claude_action: "SELL",
    claude_confidence: 0.68,
    claude_reason: "RSI過熱域（78）。短期的な反落リスクが高い。利確推奨。",
    claude_raw_response: '{"action":"SELL","confidence":0.68,"reason":"RSI過熱域..."}',
    gpt4o_action: "HOLD",
    gpt4o_confidence: 0.55,
    gpt4o_reason: "強気トレンドの中での一時的な過熱の可能性。様子見が安全。",
    gpt4o_raw_response: '{"action":"HOLD","confidence":0.55,"reason":"強気トレンドの中..."}',
    agreed: false,
    rag_context: {
      query: "BTC RSI 過熱 調整",
      chunks: ["RSI 70以上は過熱の目安...", "強気相場でのRSI過熱は継続することも多い..."],
      source_count: 2,
    },
    executed: false,
  },
  {
    id: "d004",
    timestamp: new Date(Date.now() - 1000 * 60 * 150).toISOString(),
    query: "MATIC/USDT: Polygon エコシステム拡大ニュース確認",
    final_action: "BUY",
    final_confidence: 0.79,
    claude_action: "BUY",
    claude_confidence: 0.79,
    claude_reason: "Polygon 2.0アップグレードによるネットワーク強化。中長期的にポジティブ。",
    claude_raw_response: '{"action":"BUY","confidence":0.79,"reason":"Polygon 2.0..."}',
    gpt4o_action: "BUY",
    gpt4o_confidence: 0.74,
    gpt4o_reason: "エコシステム拡大は価格上昇の材料。ポジション取得推奨。",
    agreed: true,
    executed: true,
  },
  {
    id: "d005",
    timestamp: new Date(Date.now() - 1000 * 60 * 240).toISOString(),
    query: "全体市場: 米FED金利据え置き発表後の動向分析",
    final_action: "SELL",
    final_confidence: 0.65,
    claude_action: "SELL",
    claude_confidence: 0.65,
    claude_reason: "金利据え置きは市場予想通り。ポジション整理のタイミングと判断。利確推奨。",
    claude_raw_response: '{"action":"SELL","confidence":0.65,"reason":"金利据え置き..."}',
    gpt4o_action: "HOLD",
    gpt4o_confidence: 0.58,
    gpt4o_reason: "市場の反応を確認してから判断が安全。急ぎの売却は不要。",
    agreed: false,
    executed: false,
  },
  {
    id: "d006",
    timestamp: new Date(Date.now() - 1000 * 60 * 360).toISOString(),
    query: "BTC/USDT: 週足サポートライン付近での反発確認",
    final_action: "BUY",
    final_confidence: 0.91,
    claude_action: "BUY",
    claude_confidence: 0.91,
    claude_reason: "週足の重要サポートで反発。出来高増加を確認。押し目買いの絶好タイミング。",
    claude_raw_response: '{"action":"BUY","confidence":0.91,"reason":"週足の重要サポート..."}',
    gpt4o_action: "BUY",
    gpt4o_confidence: 0.88,
    gpt4o_reason: "テクニカル的にも強いサポート帯。リスクリワード比が良好。",
    agreed: true,
    rag_context: {
      query: "BTC サポートライン 週足 反発",
      chunks: ["BTC の週足サポートは$40,000付近...", "歴史的にこのレベルからの反発率は高い..."],
      source_count: 2,
    },
    executed: true,
  },
  {
    id: "d007",
    timestamp: new Date(Date.now() - 1000 * 60 * 480).toISOString(),
    query: "ETH/USDT: Dencun アップグレード後のガス代変化影響分析",
    final_action: "HOLD",
    final_confidence: 0.55,
    claude_action: "HOLD",
    claude_confidence: 0.55,
    claude_reason: "アップグレード影響の不確実性が高い。市場が落ち着いてから判断。",
    claude_raw_response: '{"action":"HOLD","confidence":0.55,"reason":"アップグレード影響..."}',
    agreed: true,
    executed: false,
  },
  {
    id: "d008",
    timestamp: new Date(Date.now() - 1000 * 60 * 600).toISOString(),
    query: "ARB/USDT: Arbitrum エコシステム TVL 急増",
    final_action: "BUY",
    final_confidence: 0.83,
    claude_action: "BUY",
    claude_confidence: 0.83,
    claude_reason: "TVL急増はエコシステム採用の証拠。中期的な価格上昇を予想。",
    claude_raw_response: '{"action":"BUY","confidence":0.83,"reason":"TVL急増..."}',
    gpt4o_action: "BUY",
    gpt4o_confidence: 0.80,
    gpt4o_reason: "L2エコシステムの成長は継続トレンド。ARBはその恩恵を受ける。",
    agreed: true,
    rag_context: {
      query: "Arbitrum TVL 成長 エコシステム",
      chunks: ["ArbitrumのTVLは過去30日で50%増加..."],
      source_count: 1,
    },
    executed: true,
  },
];

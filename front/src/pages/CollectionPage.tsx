import { useEffect, useState } from "react";

type Sock = {
  id: string;
  level: number;
  rarity: string;
  name: string;
  comment: string;
  image: string;
  classification: {
    feature?: string;
    beauty?: number;
    special?: string;
    review?: { reason: string };
  };
};

const RARITY_STYLE: Record<number, { border: string; badge: string; glow: string }> = {
  1: { border: "#8b7355", badge: "#6b5a3e", glow: "none" },
  2: { border: "#a08060", badge: "#7a6040", glow: "none" },
  3: { border: "#6080a0", badge: "#4a6a8a", glow: "none" },
  4: { border: "#8060a0", badge: "#6a4a8a", glow: "none" },
  5: { border: "#c9a84c", badge: "#a08030", glow: "0 0 8px #c9a84c66" },
  6: { border: "#e0c060", badge: "#c0a040", glow: "0 0 12px #e0c06088" },
  7: { border: "#ff88cc", badge: "#cc5599", glow: "0 0 16px #ff88cc99" },
};

const BEAUTY_LABEL: Record<number, string> = {
  1: "★☆☆☆☆",
  2: "★★☆☆☆",
  3: "★★★☆☆",
  4: "★★★★☆",
  5: "★★★★★",
};

type Props = {
  onBack: () => void;
};

export function CollectionPage({ onBack }: Props) {
  const [socks, setSocks] = useState<Sock[]>([]);
  const [selected, setSelected] = useState<Sock | null>(null);
  const [filter, setFilter] = useState<string>("すべて");

  useEffect(() => {
    fetch("/socks-data.json")
      .then((r) => r.json())
      .then((d) => setSocks(d.items));
  }, []);

  const rarities = ["すべて", "使い古し", "素朴", "細工", "上質", "希少", "激レア", "幻"];
  const filtered = filter === "すべて" ? socks : socks.filter((s) => s.rarity === filter);

  return (
    <div className="collection-page">
      <div className="collection-header">
        <button className="back-btn" onClick={onBack}>← 戻る</button>
        <h1 className="collection-title">靴下図鑑</h1>
        <p className="collection-subtitle">60種の靴下が、あなたを待っている。</p>
      </div>

      <div className="collection-filters">
        {rarities.map((r) => (
          <button
            key={r}
            className={`filter-btn ${filter === r ? "active" : ""}`}
            onClick={() => setFilter(r)}
          >
            {r}
          </button>
        ))}
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(3, 1fr)",
        gap: "0.75rem",
        padding: "0 1.5rem 2rem",
        maxWidth: "960px",
        margin: "0 auto",
        width: "100%",
        boxSizing: "border-box",
      }}>
        {filtered.map((sock) => {
          const style = RARITY_STYLE[sock.level] ?? RARITY_STYLE[1];
          return (
            <div
              key={sock.id}
              className="sock-card"
              style={{ borderColor: style.border, boxShadow: style.glow }}
              onClick={() => setSelected(sock)}
            >
              <div className="sock-card-image">
                <img src={sock.image} alt={sock.name} />
              </div>
              <div className="sock-card-info">
                <span className="sock-rarity-badge" style={{ background: style.badge }}>
                  {sock.rarity}
                </span>
                <p className="sock-name">{sock.name}</p>
                {sock.classification.beauty && (
                  <p className="sock-beauty">{BEAUTY_LABEL[sock.classification.beauty]}</p>
                )}
                {sock.classification.feature && (
                  <span className="sock-tag">{sock.classification.feature}</span>
                )}
                {sock.classification.special && (
                  <span className="sock-tag special">{sock.classification.special}</span>
                )}
                <p className="sock-comment">{sock.comment}</p>
              </div>
            </div>
          );
        })}
      </div>

      {selected && (
        <div className="sock-modal-overlay" onClick={() => setSelected(null)}>
          <div className="sock-modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setSelected(null)}>✕</button>
            <img src={selected.image} alt={selected.name} className="modal-image" />
            <div className="modal-info">
              <span
                className="sock-rarity-badge"
                style={{ background: RARITY_STYLE[selected.level]?.badge }}
              >
                {selected.rarity}
              </span>
              <h2 className="modal-name">{selected.name}</h2>
              <p className="modal-id">{selected.id}</p>
              <p className="modal-comment">{selected.comment}</p>
              {selected.classification.feature && (
                <p className="modal-detail">印象：<strong>{selected.classification.feature}</strong></p>
              )}
              {selected.classification.beauty && (
                <p className="modal-detail">
                  綺麗さ：<strong>{BEAUTY_LABEL[selected.classification.beauty]}</strong>
                </p>
              )}
              {selected.classification.special && (
                <p className="modal-detail">特別条件：<strong>{selected.classification.special}</strong></p>
              )}
              {selected.classification.review && (
                <p className="modal-reason">「{selected.classification.review.reason}」</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** 机の上の俯瞰シーン（Image 14 のアニメ風再現・純粋SVG） */
export function DeskScene() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1320 840"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
    >
      <defs>
        {/* 机の木目グラデーション */}
        <radialGradient id="d-desk" cx="22%" cy="20%" r="72%">
          <stop offset="0%" stopColor="#f5d070" />
          <stop offset="12%" stopColor="#e8a040" />
          <stop offset="38%" stopColor="#c07030" />
          <stop offset="68%" stopColor="#8a4418" />
          <stop offset="100%" stopColor="#5a2808" />
        </radialGradient>

        {/* 窓の光オーバーレイ */}
        <radialGradient id="d-wlight" cx="20%" cy="18%" r="58%">
          <stop offset="0%" stopColor="#ffe090" stopOpacity="0.72" />
          <stop offset="38%" stopColor="#ffc840" stopOpacity="0.32" />
          <stop offset="100%" stopColor="#ffb040" stopOpacity="0" />
        </radialGradient>

        {/* 封蝋 */}
        <radialGradient id="d-wax" cx="38%" cy="32%" r="60%">
          <stop offset="0%" stopColor="#c05060" />
          <stop offset="55%" stopColor="#8b2838" />
          <stop offset="100%" stopColor="#6a1828" />
        </radialGradient>

        {/* インク壺キャップ */}
        <radialGradient id="d-cap" cx="38%" cy="30%" r="58%">
          <stop offset="0%" stopColor="#f0d070" />
          <stop offset="55%" stopColor="#c09030" />
          <stop offset="100%" stopColor="#906810" />
        </radialGradient>

        {/* 葉の影用ぼかし */}
        <filter id="d-blur4">
          <feGaussianBlur stdDeviation="4" />
        </filter>

        {/* ドロップシャドウ */}
        <filter id="d-shad" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="3" dy="5" stdDeviation="7" floodColor="#3a1808" floodOpacity="0.38" />
        </filter>
      </defs>

      {/* ── 机の木目ベース ── */}
      <rect width="1320" height="840" fill="url(#d-desk)" />

      {/* 木目の横縞 */}
      <g stroke="#6a3010" strokeWidth="1" opacity="0.055">
        {Array.from({ length: 44 }, (_, i) => (
          <line key={i} x1="0" y1={i * 19} x2="1320" y2={i * 19 + (i % 5 === 2 ? 3 : 1)} />
        ))}
      </g>

      {/* 窓からの光（上左から当たる） */}
      <rect width="1320" height="840" fill="url(#d-wlight)" />

      {/* 窓枠の影（光の縞） */}
      <g opacity="0.17" fill="#4a2008">
        <polygon points="148,0 230,0 758,840 676,840" />
        <polygon points="306,0 370,0 898,840 834,840" />
        <polygon points="454,0 510,0 1042,840 986,840" />
        <polygon points="572,0 612,0 1160,840 1120,840" />
      </g>

      {/* ── 葉の影（左上の明るい場所） ── */}
      <g filter="url(#d-blur4)" fill="#4a2008" opacity="0.3">
        <ellipse cx="318" cy="228" rx="58" ry="20" transform="rotate(-28,318,228)" />
        <ellipse cx="392" cy="192" rx="48" ry="18" transform="rotate(-33,392,192)" />
        <ellipse cx="262" cy="285" rx="52" ry="19" transform="rotate(-22,262,285)" />
        <ellipse cx="345" cy="318" rx="42" ry="16" transform="rotate(-18,345,318)" />
        <ellipse cx="440" cy="254" rx="40" ry="15" transform="rotate(-30,440,254)" />
        <ellipse cx="295" cy="175" rx="44" ry="17" transform="rotate(-38,295,175)" />
        <ellipse cx="195" cy="308" rx="35" ry="14" transform="rotate(-15,195,308)" />
        <line x1="355" y1="145" x2="248" y2="328" stroke="#4a2008" strokeWidth="5" />
        <line x1="405" y1="138" x2="355" y2="238" stroke="#4a2008" strokeWidth="4" />
        <line x1="315" y1="155" x2="262" y2="295" stroke="#4a2008" strokeWidth="3.5" />
        <line x1="448" y1="132" x2="385" y2="268" stroke="#4a2008" strokeWidth="4" />
        <line x1="230" y1="158" x2="195" y2="315" stroke="#4a2008" strokeWidth="3" />
      </g>

      {/* ── 左上：紙の束 ── */}
      <g filter="url(#d-shad)">
        <rect x="38" y="42" width="195" height="258" rx="2" fill="#ede0c0" transform="rotate(2.5,38,42)" />
        <rect x="34" y="36" width="195" height="258" rx="2" fill="#f0e8d0" transform="rotate(1,34,36)" />
        <rect x="30" y="30" width="195" height="258" rx="2" fill="#f5edd8" stroke="#d8c8a0" strokeWidth="0.8" />
        <rect x="30" y="30" width="195" height="30" rx="2" fill="rgba(255,255,255,0.18)" />
      </g>

      {/* ── 左下：リボン ── */}
      <path
        d="M 72 310 C 60 375 44 442 58 515 C 70 572 50 625 44 685 C 38 730 30 775 36 835"
        stroke="#b06878" strokeWidth="12" fill="none" strokeLinecap="round" opacity="0.88"
      />
      <path
        d="M 72 310 C 60 375 44 442 58 515 C 70 572 50 625 44 685 C 38 730 30 775 36 835"
        stroke="#d090a0" strokeWidth="7" fill="none" strokeLinecap="round" opacity="0.7"
      />
      {/* リボン上部の折り返し */}
      <path
        d="M 72 310 C 92 275 118 255 100 228"
        stroke="#b06878" strokeWidth="11" fill="none" strokeLinecap="round" opacity="0.85"
      />
      <path
        d="M 72 310 C 92 275 118 255 100 228"
        stroke="#d090a0" strokeWidth="6" fill="none" strokeLinecap="round" opacity="0.68"
      />

      {/* ── 左下：封筒 ── */}
      <g transform="translate(50,480) rotate(-6)" filter="url(#d-shad)">
        <rect x="0" y="0" width="235" height="160" rx="3" fill="#f0e8d0" stroke="#d8c8a0" strokeWidth="1" />
        {/* V字フラップ（上） */}
        <polygon points="0,0 117,82 235,0" fill="rgba(0,0,0,0.045)" />
        {/* 下フラップ */}
        <polygon points="0,160 117,82 235,160" fill="rgba(0,0,0,0.035)" />
        {/* 左右フラップ */}
        <polygon points="0,0 72,82 0,160" fill="rgba(0,0,0,0.028)" />
        <polygon points="235,0 163,82 235,160" fill="rgba(0,0,0,0.028)" />
        {/* 封蝋シール */}
        <circle cx="117" cy="80" r="30" fill="url(#d-wax)" />
        <circle cx="117" cy="80" r="24" fill="none" stroke="rgba(80,15,25,0.4)" strokeWidth="1.5" />
        <text x="117" y="86" textAnchor="middle" fontFamily="serif" fontSize="17" fill="rgba(80,15,25,0.5)">✦</text>
      </g>

      {/* ── 右上：タイプライター ── */}
      <g transform="translate(840,8)" filter="url(#d-shad)">
        {/* 机への落ち影 */}
        <ellipse cx="215" cy="308" rx="210" ry="18" fill="rgba(0,0,0,0.3)" style={{ filter: "blur(8px)" }} />

        {/* 本体下部 */}
        <rect x="28" y="285" width="374" height="22" rx="6" fill="#141420" />

        {/* メインボディ */}
        <rect x="0" y="90" width="430" height="200" rx="10" fill="#18182a" />

        {/* ゴールドトリム */}
        <rect x="0" y="88" width="430" height="5" rx="2" fill="#c9a84c" />
        <rect x="0" y="288" width="430" height="5" rx="2" fill="#c9a84c" />
        <rect x="0" y="90" width="5" height="200" fill="#c9a84c" />
        <rect x="425" y="90" width="5" height="200" fill="#c9a84c" />

        {/* サイドパネル */}
        <rect x="0" y="95" width="30" height="188" rx="8" fill="#1e1e32" />
        <rect x="400" y="95" width="30" height="188" rx="8" fill="#1e1e32" />

        {/* キャリッジ（紙ローラー） */}
        <rect x="12" y="48" width="406" height="48" rx="22" fill="#222235" stroke="#2e2e45" strokeWidth="1.5" />
        {/* ローラーノブ */}
        <circle cx="22" cy="72" r="14" fill="#252540" stroke="#383858" strokeWidth="1.5" />
        <circle cx="12" cy="72" r="10" fill="#1e1e32" />
        <circle cx="408" cy="72" r="14" fill="#252540" stroke="#383858" strokeWidth="1.5" />
        <circle cx="418" cy="72" r="10" fill="#1e1e32" />

        {/* 紙 */}
        <rect x="128" y="8" width="174" height="52" rx="2" fill="#f5edd8" stroke="#d8c8a0" strokeWidth="0.8" />
        <line x1="142" y1="22" x2="288" y2="22" stroke="#d0c098" strokeWidth="0.8" />
        <line x1="142" y1="32" x2="288" y2="32" stroke="#d0c098" strokeWidth="0.8" />
        <line x1="142" y1="42" x2="288" y2="42" stroke="#d0c098" strokeWidth="0.8" />

        {/* タイプヘッドバー */}
        <rect x="18" y="82" width="394" height="11" rx="4" fill="#252538" stroke="#303048" strokeWidth="1" />

        {/* キーボード 4行 */}
        {[0, 1, 2, 3].map((row) => (
          <g key={row} transform={`translate(${22 + row * 6},${128 + row * 38})`}>
            {Array.from({ length: 11 }, (_, col) => (
              <g key={col} transform={`translate(${col * 36},0)`}>
                <circle cx="1" cy="2" r="13" fill="rgba(0,0,0,0.5)" />
                <circle cx="0" cy="0" r="13" fill="#20202e" stroke="#c9a84c" strokeWidth="1" />
                <circle cx="0" cy="0" r="10" fill="#18182a" />
              </g>
            ))}
          </g>
        ))}

        {/* スペースバー */}
        <rect x="85" y="263" width="260" height="18" rx="7" fill="#20202e" stroke="#c9a84c" strokeWidth="1" />
      </g>

      {/* ── 右中：インク壺 ── */}
      <g transform="translate(1125,258)" filter="url(#d-shad)">
        {/* ガラスボディ */}
        <rect x="0" y="45" width="145" height="130" rx="6"
          fill="rgba(85,65,118,0.42)" stroke="rgba(180,160,120,0.45)" strokeWidth="1.5" />
        {/* インク内側 */}
        <rect x="8" y="55" width="129" height="112" rx="4" fill="#4a3068" opacity="0.92" />
        {/* ガラス光沢 */}
        <rect x="8" y="45" width="48" height="85" rx="4" fill="rgba(255,255,255,0.12)" />
        <rect x="12" y="50" width="22" height="45" rx="3" fill="rgba(255,255,255,0.08)" />
        {/* 金キャップ */}
        <ellipse cx="72" cy="45" rx="70" ry="22" fill="url(#d-cap)" />
        <ellipse cx="72" cy="38" rx="62" ry="17" fill="url(#d-cap)" />
        <ellipse cx="72" cy="22" rx="38" ry="12" fill="url(#d-cap)" />
        <ellipse cx="72" cy="16" rx="24" ry="8" fill="#d4a840" />
      </g>

      {/* ── 右：万年筆 ── */}
      <g transform="translate(1178,438) rotate(32)" filter="url(#d-shad)">
        {/* 本体（黒） */}
        <rect x="0" y="0" width="22" height="265" rx="10" fill="#18182a" />
        {/* 光沢 */}
        <rect x="2" y="5" width="6" height="200" rx="3" fill="rgba(255,255,255,0.08)" />
        {/* ゴールドバンド */}
        <rect x="-3" y="178" width="28" height="14" rx="4" fill="#c9a84c" />
        <rect x="-2" y="192" width="26" height="5" rx="2" fill="#b89038" />
        {/* クリップ */}
        <rect x="18" y="12" width="5" height="165" rx="2.5" fill="#222235" />
        <circle cx="20.5" cy="175" r="4" fill="#222235" />
        {/* ニブ */}
        <polygon points="11,265 3,310 19,310" fill="#222235" />
        <polygon points="11,282 8,310 14,310" fill="#c9a84c" />
        <ellipse cx="11" cy="311" rx="3" ry="2" fill="#c9a84c" />
      </g>

      {/* ── 右下：小花（3輪） ── */}
      {/* 花1 */}
      <g transform="translate(1072,675)">
        <g transform="rotate(0)"><ellipse cx="0" cy="-11" rx="8" ry="5" fill="#8060b0" /></g>
        <g transform="rotate(72)"><ellipse cx="0" cy="-11" rx="8" ry="5" fill="#9070c0" /></g>
        <g transform="rotate(144)"><ellipse cx="0" cy="-11" rx="8" ry="5" fill="#8060b0" /></g>
        <g transform="rotate(216)"><ellipse cx="0" cy="-11" rx="8" ry="5" fill="#9070c0" /></g>
        <g transform="rotate(288)"><ellipse cx="0" cy="-11" rx="8" ry="5" fill="#8060b0" /></g>
        <circle cx="0" cy="0" r="4.5" fill="#f5d060" />
      </g>
      {/* 花2 */}
      <g transform="translate(1128,714) rotate(-15)">
        <g transform="rotate(0)"><ellipse cx="0" cy="-10" rx="7" ry="4.5" fill="#9070c8" /></g>
        <g transform="rotate(72)"><ellipse cx="0" cy="-10" rx="7" ry="4.5" fill="#8060b8" /></g>
        <g transform="rotate(144)"><ellipse cx="0" cy="-10" rx="7" ry="4.5" fill="#9070c0" /></g>
        <g transform="rotate(216)"><ellipse cx="0" cy="-10" rx="7" ry="4.5" fill="#8060b8" /></g>
        <g transform="rotate(288)"><ellipse cx="0" cy="-10" rx="7" ry="4.5" fill="#9070c0" /></g>
        <circle cx="0" cy="0" r="4" fill="#f5d060" />
      </g>
      {/* 花3（小） */}
      <g transform="translate(1168,688) rotate(8)">
        <g transform="rotate(0)"><ellipse cx="0" cy="-9" rx="6" ry="4" fill="#a080d0" /></g>
        <g transform="rotate(72)"><ellipse cx="0" cy="-9" rx="6" ry="4" fill="#9070c0" /></g>
        <g transform="rotate(144)"><ellipse cx="0" cy="-9" rx="6" ry="4" fill="#a080d0" /></g>
        <g transform="rotate(216)"><ellipse cx="0" cy="-9" rx="6" ry="4" fill="#9070c0" /></g>
        <g transform="rotate(288)"><ellipse cx="0" cy="-9" rx="6" ry="4" fill="#a080d0" /></g>
        <circle cx="0" cy="0" r="3.5" fill="#f5d060" />
      </g>
    </svg>
  );
}

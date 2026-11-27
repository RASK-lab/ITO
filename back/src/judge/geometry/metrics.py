"""形・バランス・線質・終筆の各指標（距離を返す。点数化は score.py）。"""

from __future__ import annotations

import numpy as np

from .normalize import PreparedStroke, arc_length, resample

_EPS = 1e-9


# ---------- 形 ----------

def procrustes_align(user_pts: np.ndarray, ref_pts: np.ndarray) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    """user_pts を ref_pts に相似変換（回転・拡大・平行移動、鏡像なし）で重ねる。

    返り値: (変換後の user_pts, scale, 回転行列 R, 平行移動 t)。x' = scale * (x - mu_u) @ R + mu_r
    """
    mu_u, mu_r = user_pts.mean(axis=0), ref_pts.mean(axis=0)
    U0, R0 = user_pts - mu_u, ref_pts - mu_r
    H = U0.T @ R0
    u, s, vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(u @ vt))
    D = np.diag([1.0, d])
    rot = u @ D @ vt
    denom = float((U0 ** 2).sum())
    scale = float((s * np.diag(D)).sum() / denom) if denom > _EPS else 1.0
    aligned = scale * U0 @ rot + mu_r
    return aligned, scale, rot, mu_r - scale * mu_u @ rot


def apply_transform(pts: np.ndarray, scale: float, rot: np.ndarray, mu_u: np.ndarray, mu_r: np.ndarray) -> np.ndarray:
    return scale * (pts - mu_u) @ rot + mu_r


def dtw_distance(a: np.ndarray, b: np.ndarray) -> float:
    """DTW 距離を経路長で割った平均距離。"""
    D = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=-1)
    n, m = D.shape
    acc = np.full((n + 1, m + 1), np.inf)
    acc[0, 0] = 0.0
    steps = np.zeros((n + 1, m + 1))
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            choices = (acc[i - 1, j - 1], acc[i - 1, j], acc[i, j - 1])
            k = int(np.argmin(choices))
            prev = [(i - 1, j - 1), (i - 1, j), (i, j - 1)][k]
            acc[i, j] = D[i - 1, j - 1] + choices[k]
            steps[i, j] = steps[prev] + 1
    return float(acc[n, m] / max(steps[n, m], 1))


def shape_distances(
    user: list[PreparedStroke], ref: list[np.ndarray], pairs: list[tuple[int, int]], reversed_: dict[int, bool]
) -> dict[int, float]:
    """対応した画の点をまとめて Procrustes で重ねたあと、画ごとの DTW 平均距離を返す（キー: user_index）。"""
    if not pairs:
        return {}
    U = [user[i].resampled[::-1] if reversed_[i] else user[i].resampled for i, _ in pairs]
    R = [ref[j] for _, j in pairs]
    allu, allr = np.concatenate(U), np.concatenate(R)
    mu_u, mu_r = allu.mean(axis=0), allr.mean(axis=0)
    _, scale, rot, _ = procrustes_align(allu, allr)
    out = {}
    for (i, _), u, r in zip(pairs, U, R):
        out[i] = dtw_distance(apply_transform(u, scale, rot, mu_u, mu_r), r)
    return out


# ---------- バランス ----------

def balance_distance(user: list[PreparedStroke], ref: list[np.ndarray], pairs: list[tuple[int, int]]) -> float:
    """位置合わせなし（正規化のみ）で、画ごとの重心と大きさのずれを平均する。"""
    if not pairs:
        return 1.0
    ds = []
    for i, j in pairs:
        u, r = user[i].resampled, ref[j]
        dc = np.linalg.norm(u.mean(axis=0) - r.mean(axis=0))
        ds_size = np.abs((u.max(axis=0) - u.min(axis=0)) - (r.max(axis=0) - r.min(axis=0))).mean()
        ds.append(dc + 0.5 * ds_size)
    return float(np.mean(ds))


# ---------- 線質 ----------

def line_jitter(user: list[PreparedStroke], spacing: float = 0.015) -> float:
    """生の点を一定間隔に取り直し、進行方向の変化量のばらつき（ガタつき）を測る。"""
    vals = []
    for s in user:
        if s.length < spacing * 6:
            continue
        n = max(int(s.length / spacing), 6)
        p = resample(s.raw, n)
        v = np.diff(p, axis=0)
        ang = np.unwrap(np.arctan2(v[:, 1], v[:, 0]))
        turn = np.diff(ang)
        if len(turn) < 3:
            continue
        vals.append(float(np.abs(np.diff(turn)).mean()))
    return float(np.mean(vals)) if vals else 0.0


# ---------- 終筆（止め・はね・払い） ----------

def classify_ending(s: PreparedStroke) -> str:
    """終端の速度と方向転換から tome / hane / harai / unknown を判定する。"""
    xy, t = s.raw, s.t
    if len(xy) < 5 or s.length < 0.05:
        return "unknown"
    dt = np.diff(t)
    if np.all(dt <= 0):
        return "unknown"  # 時刻が無い
    cum = arc_length(xy)
    L = cum[-1]

    # はね: 最後の 15% 以内で進行方向が 60° 以上折れ返っているか
    tail_start = np.searchsorted(cum, L * 0.85)
    body_start = np.searchsorted(cum, L * 0.6)
    if tail_start < len(xy) - 1 and body_start < tail_start:
        v_body = xy[tail_start] - xy[body_start]
        v_tail = xy[-1] - xy[tail_start]
        nb, nt = np.linalg.norm(v_body), np.linalg.norm(v_tail)
        if nb > _EPS and nt > L * 0.03:
            cos = float(v_body @ v_tail / (nb * nt))
            if cos < np.cos(np.deg2rad(60)):
                return "hane"

    # 止め / 払い: 終端 10% の速さと全体の速さの比
    seg = np.diff(cum)
    good = dt > 0
    if good.sum() < 3:
        return "unknown"
    speed = np.zeros_like(seg)
    speed[good] = seg[good] / dt[good]
    v_med = float(np.median(speed[good]))
    if v_med < _EPS:
        return "unknown"
    end_idx = np.searchsorted(cum, L * 0.9)
    tail = speed[max(end_idx - 1, 0):][good[max(end_idx - 1, 0):]]
    if len(tail) == 0:
        return "unknown"
    ratio = float(tail.mean()) / v_med
    if ratio < 0.45:
        return "tome"
    if ratio > 0.75:
        return "harai"
    return "unknown"

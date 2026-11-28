/**
 * ペンの入力の調査用の記録（アドレスに ?debug=pen を付けて開いたときだけ動く）。
 *
 * iPad の Apple Pencil で線が乱れる原因を、推定ではなく実機の値で確かめるためのもの。
 * 端末が報告した値（位置・時刻・筆圧）を、手を加えずに覚え、書き終えた線 1 本ぶんを
 * 文字にまとめる。線の描画や、記録して送るデータには関わらない。
 */

/** 調査用の表示を出すか。ページを開いたときのアドレスで決める（あとで # が変わっても同じ）。 */
export const PEN_DEBUG =
  new URLSearchParams(window.location.search).get("debug") === "pen";

/** 端末が報告した 1 点。[clientX, clientY, timeStamp, pressure]（丸める前の値） */
type Sample = [x: number, y: number, t: number, pressure: number];

/** pointermove の通知 1 回ぶん */
type Move = {
  /** 通知そのものの点 */
  e: Sample;
  /** まとめて届いた点（getCoalescedEvents() の結果）。この機能がないブラウザでは null。 */
  c: Sample[] | null;
  /** 先読みの点（getPredictedEvents() の結果）の数。この機能がないブラウザでは -1。 */
  predicted: number;
  /** 通知を受け取った時刻（performance.now()）。通知の時刻とのずれを見る。 */
  now: number;
};

/** 押してから離すまでの 1 本の線の記録 */
export type PenDebugStroke = {
  /** 端末が報告した入力の種類（pen / touch / mouse など） */
  type: string;
  pointerId: number;
  down: Sample;
  moves: Move[];
  up: Sample | null;
  /** 線を終えた通知の種類（pointerup / pointercancel / lostpointercapture） */
  end: string;
};

/** JSON に入れておく線の本数（直近のものだけ） */
const KEPT_STROKES = 3;
/** 表示する値の個数（筆圧と時刻の差の、先頭から） */
const SHOWN_VALUES = 40;

function toSample(event: PointerEvent): Sample {
  return [event.clientX, event.clientY, event.timeStamp, event.pressure];
}

export function startPenDebugStroke(event: PointerEvent): PenDebugStroke {
  return {
    type: event.pointerType,
    pointerId: event.pointerId,
    down: toSample(event),
    moves: [],
    up: null,
    end: "",
  };
}

/** @param coalesced getCoalescedEvents() の結果。この機能がないブラウザでは undefined。 */
export function recordPenDebugMove(
  stroke: PenDebugStroke,
  event: PointerEvent,
  coalesced: PointerEvent[] | undefined,
) {
  stroke.moves.push({
    e: toSample(event),
    c: coalesced ? coalesced.map(toSample) : null,
    predicted: event.getPredictedEvents?.().length ?? -1,
    now: performance.now(),
  });
}

export function endPenDebugStroke(stroke: PenDebugStroke, event: PointerEvent) {
  stroke.end = event.type;
  if (event.type === "pointerup") stroke.up = toSample(event);
}

/** 直近の線だけを残す */
export function keepPenDebugStrokes(strokes: PenDebugStroke[]) {
  return strokes.slice(-KEPT_STROKES);
}

function round(value: number, digits: number) {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

/** 筆圧を短く書く（0.12 → .12） */
function formatPressure(value: number) {
  return value.toFixed(2).replace(/^0\./, ".");
}

function summarize(values: number[], format: (value: number) => string) {
  if (values.length === 0) return "なし";
  const sum = values.reduce((a, b) => a + b, 0);
  return `最小${format(Math.min(...values))} 最大${format(Math.max(...values))} 平均${format(sum / values.length)}`;
}

function differences(values: number[]) {
  return values.slice(1).map((value, i) => value - values[i]);
}

/** 進む向きが 90 度以上変わった回数（同じ座標の点は飛ばして数える） */
function countTurnBacks(samples: Sample[]) {
  let count = 0;
  let previous: [number, number] | null = null;
  let last = samples[0];
  for (const sample of samples.slice(1)) {
    const step: [number, number] = [sample[0] - last[0], sample[1] - last[1]];
    if (step[0] === 0 && step[1] === 0) continue;
    if (previous && previous[0] * step[0] + previous[1] * step[1] < 0) count++;
    previous = step;
    last = sample;
  }
  return count;
}

/** 直前の点と同じ座標の点の数 */
function countSamePositions(samples: Sample[]) {
  return samples.filter(
    (sample, i) =>
      i > 0 && sample[0] === samples[i - 1][0] && sample[1] === samples[i - 1][1],
  ).length;
}

/** 束の中の順番ごとの、筆圧の平均（fromEnd が true なら後ろから数える） */
function pressureByOrder(batches: Sample[][], fromEnd: boolean) {
  const sums: number[] = [];
  const counts: number[] = [];
  for (const batch of batches) {
    const ordered = fromEnd ? [...batch].reverse() : batch;
    ordered.slice(0, 5).forEach((sample, i) => {
      sums[i] = (sums[i] ?? 0) + sample[3];
      counts[i] = (counts[i] ?? 0) + 1;
    });
  }
  return sums.map((sum, i) => formatPressure(sum / counts[i])).join(" ");
}

/**
 * 線 1 本ぶんの記録を、画面に出す文字にまとめる。
 *
 * @param number 何本目の線か（1 から）
 * @param canvasSize 枠の一辺（CSS のピクセル）
 */
export function describePenDebugStroke(
  stroke: PenDebugStroke,
  number: number,
  canvasSize: number,
) {
  const { moves } = stroke;
  const ms = (value: number) => value.toFixed(1);
  const notified = moves.map((move) => move.e);
  const batches = moves.map((move) => move.c ?? []);
  const filled = moves.filter((move) => move.c !== null && move.c.length > 0);
  const coalesced = batches.flat();
  // アプリが線に足している点（まとめて届いた点があればそれ、なければ通知の点）
  const used = [
    stroke.down,
    ...moves.flatMap((move) => (move.c && move.c.length > 0 ? move.c : [move.e])),
  ];
  const usedTimeSteps = differences(used.map((sample) => sample[2]));
  const notifiedTimeSteps = differences(
    [stroke.down, ...notified].map((sample) => sample[2]),
  );
  const lastOf = (move: Move) => (move.c as Sample[])[(move.c as Sample[]).length - 1];
  const matches = (index: 0 | 2 | 3) =>
    filled.filter((move) => lastOf(move)[index] === move.e[index]).length;
  const samePosition = filled.filter(
    (move) => lastOf(move)[0] === move.e[0] && lastOf(move)[1] === move.e[1],
  ).length;
  const anywhere = filled.filter((move) =>
    (move.c as Sample[]).some((s) => s[0] === move.e[0] && s[1] === move.e[1]),
  ).length;
  // 束の最初の点が、前の束の最後の点と同じ位置か（同じ点が 2 回届いていないか）
  let repeated = 0;
  for (let i = 1; i < batches.length; i++) {
    const previous = batches[i - 1][batches[i - 1].length - 1];
    const first = batches[i][0];
    if (previous && first && previous[0] === first[0] && previous[1] === first[1])
      repeated++;
  }
  // 前の通知までに届いた点が、もう一度届いていないか（時刻が、それまでの最後の時刻以下の点）
  let replayed = 0;
  let replayedMoves = 0;
  let latest = stroke.down[2];
  for (const batch of batches) {
    const count = batch.filter((sample) => sample[2] <= latest).length;
    replayed += count;
    if (count > 0) replayedMoves++;
    latest = Math.max(latest, ...batch.map((sample) => sample[2]));
  }
  const predicted = moves.map((move) => move.predicted);
  const pressureLine = (samples: Sample[]) => {
    const values = samples.map((sample) => sample[3]);
    return `${summarize(values, formatPressure)} 0の数${values.filter((v) => v === 0).length}`;
  };
  // まとめて届いた点の筆圧を、通知の区切り（|）を入れて並べる
  const coalescedPressures: string[] = [];
  for (const batch of batches) {
    if (coalescedPressures.length >= SHOWN_VALUES) break;
    coalescedPressures.push(batch.map((s) => formatPressure(s[3])).join(" "));
  }
  const coalescedTimes: string[] = [];
  let shown = 0;
  for (let i = 0; i < batches.length && shown < SHOWN_VALUES; i++) {
    const before = i === 0 ? stroke.down : (batches[i - 1].at(-1) ?? moves[i - 1].e);
    const times = [before, ...batches[i]].map((sample) => sample[2]);
    coalescedTimes.push(differences(times).map(ms).join(" "));
    shown += batches[i].length;
  }
  const countOf = (values: number[], test: (value: number) => boolean) =>
    values.filter(test).length;

  return [
    `線${number}本目 種類 ${stroke.type}(id ${stroke.pointerId}) 終わり ${stroke.end}`,
    `まとめて届く点の機能 ${moves.some((m) => m.c !== null) ? "あり" : moves.length ? "なし" : "?"} / 先読みの点 ${predicted.length ? summarize(predicted, (v) => String(round(v, 1))) : "?"}`,
    `通知 ${moves.length}回 間隔ms ${summarize(notifiedTimeSteps, ms)} 0の数${countOf(notifiedTimeSteps, (v) => v === 0)} 負の数${countOf(notifiedTimeSteps, (v) => v < 0)}`,
    `まとめて届いた点 計${coalesced.length} 1回あたり ${summarize(batches.map((b) => b.length), (v) => String(round(v, 1)))} 空${moves.length - filled.length}回`,
    `最後の点=通知の点: 位置${samePosition} 筆圧${matches(3)} 時刻${matches(2)} /${filled.length}回 (どこかに同じ位置 ${anywhere})`,
    `前の通知までの点と重なる点(時刻が戻る): ${replayed}個/${coalesced.length} (${replayedMoves}回の通知で)`,
    `束の最初の点=前の束の最後の点(位置): ${repeated}回`,
    `通知の時刻-最後の点の時刻ms: ${summarize(filled.map((m) => m.e[2] - lastOf(m)[2]), ms)}`,
    `受け取り-通知の時刻ms: ${summarize(moves.map((m) => m.now - m.e[2]), ms)}`,
    `筆圧 down ${formatPressure(stroke.down[3])} up ${stroke.up ? formatPressure(stroke.up[3]) : "-"}`,
    `筆圧 通知: ${pressureLine(notified)}`,
    notified.slice(0, SHOWN_VALUES).map((s) => formatPressure(s[3])).join(" "),
    `筆圧 まとめ(|は通知の区切り): ${pressureLine(coalesced)}`,
    coalescedPressures.join("|"),
    `束の中の順番ごとの平均筆圧 前から: ${pressureByOrder(batches, false)}`,
    `  後ろから: ${pressureByOrder(batches, true)}`,
    `線の点の時刻の差ms: ${summarize(usedTimeSteps, ms)} 0の数${countOf(usedTimeSteps, (v) => v === 0)} 負の数${countOf(usedTimeSteps, (v) => v < 0)}`,
    coalescedTimes.join("|"),
    `逆戻り(90度以上): 線の点${countTurnBacks(used)}回 通知${countTurnBacks([stroke.down, ...notified])}回`,
    `同じ座標: 線の点${countSamePositions(used)}個/${used.length} 通知${countSamePositions([stroke.down, ...notified])}個/${notified.length + 1}`,
    `枠${round(canvasSize, 1)}px 画素密度${window.devicePixelRatio} 画面${window.innerWidth}x${window.innerHeight}`,
    navigator.userAgent,
  ].join("\n");
}

/** 覚えている線の記録を、JSON の文字にする（送ってもらって、あとで調べるためのもの） */
export function penDebugJson(strokes: PenDebugStroke[], canvasSize: number) {
  const compact = (sample: Sample) => [
    round(sample[0], 2),
    round(sample[1], 2),
    round(sample[2], 2),
    round(sample[3], 4),
  ];
  return JSON.stringify({
    userAgent: navigator.userAgent,
    devicePixelRatio: window.devicePixelRatio,
    window: [window.innerWidth, window.innerHeight],
    canvasSize: round(canvasSize, 1),
    // 点は [clientX, clientY, timeStamp, pressure]
    strokes: strokes.map((stroke) => ({
      type: stroke.type,
      pointerId: stroke.pointerId,
      end: stroke.end,
      down: compact(stroke.down),
      up: stroke.up && compact(stroke.up),
      moves: stroke.moves.map((move) => ({
        e: compact(move.e),
        c: move.c && move.c.map(compact),
        predicted: move.predicted,
        now: round(move.now, 2),
      })),
    })),
  });
}

/** 文字をクリップボードに入れる。入れられたら true。 */
export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // アプリの中のブラウザなど、クリップボードの機能が使えないときは、古い方法を試す
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    const copied = document.execCommand("copy");
    area.remove();
    return copied;
  }
}

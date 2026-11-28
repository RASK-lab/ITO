import { useEffect, useImperativeHandle, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, Ref } from "react";
import { getStroke } from "perfect-freehand";
import {
  PEN_DEBUG,
  copyText,
  describePenDebugStroke,
  endPenDebugStroke,
  keepPenDebugStrokes,
  penDebugJson,
  recordPenDebugMove,
  startPenDebugStroke,
} from "../penDebug";
import type { PenDebugStroke } from "../penDebug";

/** 入力の種類 */
export type PointerType = "mouse" | "touch" | "pen";

/**
 * 画面に描くために覚えておく点。x, y は枠の一辺を 1 とした位置（枠の画素数が
 * 変わっても同じ形で描き直せる）。t は最初の線を書きはじめてからの経過ミリ秒。
 * pressure は筆圧（0〜1）。
 */
type Point = { x: number; y: number; t: number; pressure: number };
/**
 * ポインタを押してから離すまでの 1 本の線。pointerType は書きはじめたときの種類。
 * points は、記録して送る点（端末から届いた点のすべて）。
 * drawn は、線を描くのに使う点。ペンでは points より粗い（理由は toPath を参照）。
 * マウスと指では points と同じ配列。
 */
type Stroke = { pointerType: PointerType; points: Point[]; drawn: Point[] };

/**
 * 記録する点。[x, y, t, pressure] の並び（分析側の資料に合わせた形。docs/api.md）。
 * x, y は枠の左上を (0, 0)、一辺を STROKE_CANVAS_SIZE とした位置。
 */
export type RecordedPoint = [x: number, y: number, t: number, pressure: number];
export type RecordedStroke = {
  pointerType: PointerType;
  points: RecordedPoint[];
};

export type Drawing = {
  /** 白地に黒で描いた PNG の data URL。正方形で、一辺は MIN_IMAGE_SIZE 以上。 */
  image: string;
  /** 画像の画素数（枠の画素数と同じとは限らない） */
  width: number;
  height: number;
  /** 線の座標の基準にした枠の大きさ。画面の大きさに関係なく、いつも同じ。 */
  canvas: { width: number; height: number };
  strokes: RecordedStroke[];
};

export type WritingCanvasHandle = {
  /** すべて消す */
  clear: () => void;
  /** 最後に書いた線を 1 本取り消す */
  undo: () => void;
  /** 何も書かれていなければ null */
  exportDrawing: () => Drawing | null;
};

type Props = {
  ref?: Ref<WritingCanvasHandle>;
  /** true の間は新しい線を書けない */
  disabled?: boolean;
  /**
   * 線の本数が変わったときと、上限に達して書けなかったときに呼ばれる。
   * full は、点の合計が上限に達していて、これ以上書けないとき true。
   */
  onChange?: (strokeCount: number, full: boolean) => void;
};

/** 枠の一辺に対する線の太さ（筆圧が真ん中のときの太さ） */
const LINE_WIDTH_RATIO = 0.02;
/**
 * 線の書き味（perfect-freehand に渡す値。どれも 0〜1）。
 * thinning: 筆圧で太さが変わる幅。0.6 なら、太さは LINE_WIDTH_RATIO の 0.4〜1.6 倍。
 * smoothing: 線のふちのなめらかさ。
 * streamline: 手ぶれの補正。大きいほどなめらかだが、線が手の動きから遅れる。
 */
const STROKE_OPTIONS = { thinning: 0.6, smoothing: 0.5, streamline: 0.5 };
/**
 * 覚える位置の範囲。枠の外へ出た線は、枠の一辺ぶん外側で止める
 * （記録する座標では -1024〜2048。API の受け入れ範囲と同じ）。
 */
const MIN_POSITION = -1;
const MAX_POSITION = 2;
/**
 * 記録する線の座標の基準にする枠の一辺。画面の枠が何ピクセルでも、枠をこの大きさと
 * みなした座標で送る（バックエンドが保存する大きいほうの画像と同じ基準）。
 * API が受け取る値（back/src/drawings.py の CANVAS_SIZE）と同じ値にする。
 */
const STROKE_CANVAS_SIZE = 1024;
/**
 * マウスで書いた点の筆圧。マウスは筆圧を測れず、ブラウザは、押している間は 0.5、
 * ボタンを離した瞬間は 0 と報告する。その値は使わず、いつもこの値にする。
 */
const MOUSE_PRESSURE = 0.5;
/**
 * 書ける点の合計の上限。線の本数には上限を置かない。
 * API が受け取る上限（back/src/drawings.py の MAX_POINTS）と同じ値にする。
 */
const MAX_POINTS = 200_000;
/**
 * 送る画像の一辺（ピクセル）の下限と上限。
 * バックエンドは、受け取った画像を縮小して保存する。小さい画像を引き伸ばすとぼやけるので、
 * 枠の画素数が下限より小さいときも、下限の大きさで描き起こして送る。
 * API が受け取る範囲（back/src/drawings.py の MIN_IMAGE_SIZE と MAX_IMAGE_SIZE）と同じ値にする。
 */
const MIN_IMAGE_SIZE = 1024;
const MAX_IMAGE_SIZE = 4096;

function toPosition(value: number) {
  return Math.min(MAX_POSITION, Math.max(MIN_POSITION, value));
}

/** ペンと指のほか（種類がわからないものを含む）は、マウスとして扱う */
function toPointerType(event: PointerEvent): PointerType {
  return event.pointerType === "pen" || event.pointerType === "touch"
    ? event.pointerType
    : "mouse";
}

/** ペンと指は、端末が報告する筆圧をそのまま使う */
function toPressure(event: PointerEvent, pointerType: PointerType) {
  if (pointerType === "mouse") return MOUSE_PRESSURE;
  return Math.min(1, Math.max(0, event.pressure));
}

/**
 * 覚えている点を、記録する形にする。送る JSON を小さくするため、位置は小数 1 桁、
 * 経過ミリ秒は整数、筆圧は小数 2 桁に丸める。
 */
function toRecordedPoint(point: Point): RecordedPoint {
  return [
    Math.round(point.x * STROKE_CANVAS_SIZE * 10) / 10,
    Math.round(point.y * STROKE_CANVAS_SIZE * 10) / 10,
    Math.round(point.t),
    Math.round(point.pressure * 100) / 100,
  ];
}

function countPoints(strokes: Stroke[]) {
  return strokes.reduce((count, stroke) => count + stroke.points.length, 0);
}

/**
 * 1 本の線の形（ふちをなぞった、塗りつぶす形）を作る。太さは筆圧で変える。
 * ペンは、端末が報告した筆圧を使う。マウスと指は筆圧を測れないので、書く速さから作る
 * （ゆっくりは太く、速いと細い）。
 *
 * 描くのに使う点は stroke.drawn。ペンでは、pointermove の通知そのものの点（画面の更新
 * 1 回につき 1 点）だけが入っていて、まとめて届いた細かい点（getCoalescedEvents）は
 * 入っていない。iPad の Apple Pencil で、細かい点まで使って描くと、線が数珠つなぎに
 * くびれたり、点々が並んだりした（筆圧をならしても残った）。通知そのものの点だけで描くのは、
 * 多くの手書きの実装と同じやり方。細かい点は、記録（stroke.points）には残している。
 * 筆圧は加工しない。
 *
 * @param finished 書き終えた線なら true。書いている途中の線は、終わりの形がまだ決まらない。
 */
function toPath(stroke: Stroke, size: number, finished: boolean) {
  const outline = getStroke(
    stroke.drawn.map((p) => [p.x * size, p.y * size, p.pressure]),
    {
      ...STROKE_OPTIONS,
      size: size * LINE_WIDTH_RATIO,
      simulatePressure: stroke.pointerType !== "pen",
      last: finished,
    },
  );
  const path = new Path2D();
  if (outline.length === 0) return path;
  // ふちの点を、角が出ないよう曲線でつなぐ
  path.moveTo(outline[0][0], outline[0][1]);
  outline.forEach(([x, y], i) => {
    const [nextX, nextY] = outline[(i + 1) % outline.length];
    path.quadraticCurveTo(x, y, (x + nextX) / 2, (y + nextY) / 2);
  });
  path.closePath();
  return path;
}

/**
 * 書き終えた線の形の控え。線を足すたびに全部を描き直すので、書き終えた線の形は作り直さない。
 * 枠の大きさ（size）が変わったら作り直す。
 */
const pathCache = new WeakMap<Stroke, { size: number; path: Path2D }>();

/**
 * 線を描く。
 *
 * @param active 書いている途中の線。形が毎回変わるので、控えを使わない。
 */
function drawStrokes(
  ctx: CanvasRenderingContext2D,
  strokes: Stroke[],
  size: number,
  color: string,
  active?: Stroke,
) {
  ctx.fillStyle = color;
  for (const stroke of strokes) {
    if (stroke === active) {
      ctx.fill(toPath(stroke, size, false));
      continue;
    }
    let cached = pathCache.get(stroke);
    if (cached?.size !== size) {
      cached = { size, path: toPath(stroke, size, true) };
      pathCache.set(stroke, cached);
    }
    ctx.fill(cached.path);
  }
}

/** 線の色は CSS の color で決める（デザインを入れるときに CSS だけで変えられる） */
function inkColor(canvas: HTMLCanvasElement) {
  return getComputedStyle(canvas).color;
}

/**
 * 全部の線を描き直す。線の形は、点が足されるたびに書きはじめまでさかのぼって変わるので、
 * 足した分だけを描き足すことはできない。
 */
function redraw(
  canvas: HTMLCanvasElement | null,
  strokes: Stroke[],
  active?: Stroke,
) {
  const ctx = canvas?.getContext("2d");
  if (!canvas || !ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawStrokes(ctx, strokes, canvas.width, inkColor(canvas), active);
}

/** 表示の大きさと画面の画素密度に、描画用の画素数を合わせる */
function fitToDisplay(canvas: HTMLCanvasElement, strokes: Stroke[]) {
  const size = Math.round(canvas.clientWidth * window.devicePixelRatio);
  if (size === 0 || (size === canvas.width && size === canvas.height)) return;
  canvas.width = size;
  canvas.height = size;
  redraw(canvas, strokes);
}

export function WritingCanvas({ ref, disabled, onChange }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const strokesRef = useRef<Stroke[]>([]);
  /** いま覚えている点の合計 */
  const pointCountRef = useRef(0);
  const activeRef = useRef<{ pointerId: number; stroke: Stroke } | null>(null);
  const startedAtRef = useRef<number | null>(null);
  // ここから 4 つは、ペンの入力の調査用（アドレスに ?debug=pen を付けたときだけ使う。penDebug.ts）
  const debugActiveRef = useRef<PenDebugStroke | null>(null);
  const debugStrokesRef = useRef<PenDebugStroke[]>([]);
  const [debugText, setDebugText] = useState("");
  const [debugCopied, setDebugCopied] = useState("");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const fit = () => fitToDisplay(canvas, strokesRef.current);
    // 枠の大きさが変わったとき
    const observer = new ResizeObserver(fit);
    observer.observe(canvas);
    // ブラウザの拡大・縮小で、画素密度だけが変わったとき
    window.addEventListener("resize", fit);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", fit);
    };
  }, []);

  function notifyChange() {
    onChange?.(strokesRef.current.length, pointCountRef.current >= MAX_POINTS);
  }

  useImperativeHandle(ref, () => {
    function setStrokes(strokes: Stroke[]) {
      strokesRef.current = strokes;
      pointCountRef.current = countPoints(strokes);
      activeRef.current = null;
      if (strokes.length === 0) startedAtRef.current = null;
      redraw(canvasRef.current, strokes);
      notifyChange();
    }
    return {
      clear: () => setStrokes([]),
      undo: () => setStrokes(strokesRef.current.slice(0, -1)),
      exportDrawing() {
        const canvas = canvasRef.current;
        const strokes = strokesRef.current;
        if (!canvas || strokes.length === 0) return null;
        // 画面の枠を写すのではなく、覚えている線から描き起こす。
        // 一辺は、枠の画素数と下限の大きいほう（線は枠に対する割合で覚えているので、
        // どの大きさでも同じ形になる）。
        const size = Math.min(
          MAX_IMAGE_SIZE,
          Math.max(MIN_IMAGE_SIZE, canvas.width),
        );
        const out = document.createElement("canvas");
        out.width = size;
        out.height = size;
        const ctx = out.getContext("2d");
        if (!ctx) return null;
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, size, size);
        drawStrokes(ctx, strokes, size, "#000");
        return {
          image: out.toDataURL("image/png"),
          width: size,
          height: size,
          canvas: { width: STROKE_CANVAS_SIZE, height: STROKE_CANVAS_SIZE },
          strokes: strokes.map((stroke) => ({
            pointerType: stroke.pointerType,
            points: stroke.points.map(toRecordedPoint),
          })),
        };
      },
    };
  });

  function toPoint(
    event: PointerEvent,
    canvas: HTMLCanvasElement,
    startedAt: number,
    pressure: number,
  ): Point {
    const rect = canvas.getBoundingClientRect();
    return {
      x: toPosition(
        (event.clientX - rect.left - canvas.clientLeft) / canvas.clientWidth,
      ),
      y: toPosition(
        (event.clientY - rect.top - canvas.clientTop) / canvas.clientHeight,
      ),
      t: Math.max(0, event.timeStamp - startedAt),
      pressure,
    };
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLCanvasElement>) {
    // 左ボタンだけで書く。書いている途中の別のポインタは無視する。
    if (disabled || activeRef.current || event.button !== 0) return;
    // 上限に達していたら書きはじめない。案内を出し直せるよう、書けなかったことを知らせる。
    if (pointCountRef.current >= MAX_POINTS) {
      notifyChange();
      return;
    }
    const canvas = event.currentTarget;
    // 画面を別のディスプレイへ移したあとなど、画素密度が変わっていたら合わせ直す
    fitToDisplay(canvas, strokesRef.current);
    canvas.setPointerCapture(event.pointerId);
    startedAtRef.current ??= event.timeStamp;
    const native = event.nativeEvent;
    const pointerType = toPointerType(native);
    const first = toPoint(
      native,
      canvas,
      startedAtRef.current,
      toPressure(native, pointerType),
    );
    const points = [first];
    const stroke: Stroke = {
      pointerType,
      points,
      // ペンは、描くのに使う点を別に持つ。マウスと指は、記録する点をそのまま描く。
      drawn: pointerType === "pen" ? [first] : points,
    };
    activeRef.current = { pointerId: event.pointerId, stroke };
    strokesRef.current = [...strokesRef.current, stroke];
    if (PEN_DEBUG) debugActiveRef.current = startPenDebugStroke(native);
    pointCountRef.current += 1;
    // この 1 点で上限に達したら、線はここで終える
    if (pointCountRef.current >= MAX_POINTS) activeRef.current = null;
    redraw(canvas, strokesRef.current, activeRef.current?.stroke);
    notifyChange();
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    const active = activeRef.current;
    const startedAt = startedAtRef.current;
    if (!active || active.pointerId !== event.pointerId || startedAt === null)
      return;
    // 「離した」が届かないまま左ボタンが上がっていたら、そこで線を終える
    // （右クリックのメニューが出たときなど）
    if ((event.buttons & 1) === 0) {
      activeRef.current = null;
      redraw(event.currentTarget, strokesRef.current);
      return;
    }
    const canvas = event.currentTarget;
    // 画面の更新より細かく届いた点も覚える（マウスと指は、速く書いても線が角ばらないよう、
    // 描くのにも使う。ペンは、記録にだけ使う）
    const native = event.nativeEvent;
    const coalesced = native.getCoalescedEvents?.();
    const events = coalesced ?? [];
    if (PEN_DEBUG && debugActiveRef.current)
      recordPenDebugMove(debugActiveRef.current, native, coalesced);
    const { pointerType, points, drawn } = active.stroke;
    // 上限までの残りの分だけ足す（書いている途中の線があるとき、残りは必ず 1 以上）
    const added = (events.length > 0 ? events : [native])
      .slice(0, MAX_POINTS - pointCountRef.current)
      .map((e) => toPoint(e, canvas, startedAt, toPressure(e, pointerType)));
    points.push(...added);
    pointCountRef.current += added.length;
    // ペンの線を描くのに使うのは、通知そのものの点だけ（上限の数には入れない）
    if (drawn !== points) {
      drawn.push(
        toPoint(native, canvas, startedAt, toPressure(native, pointerType)),
      );
    }
    // 上限に達したら、押したままでも線をそこで終える
    if (pointCountRef.current >= MAX_POINTS) {
      activeRef.current = null;
      notifyChange();
    }
    redraw(canvas, strokesRef.current, activeRef.current?.stroke);
  }

  /** 調査用: 書き終えた線の記録をまとめて、表示を入れ替える */
  function finishPenDebugStroke(event: PointerEvent) {
    const stroke = debugActiveRef.current;
    if (!stroke) return;
    debugActiveRef.current = null;
    endPenDebugStroke(stroke, event);
    debugStrokesRef.current = keepPenDebugStrokes([
      ...debugStrokesRef.current,
      stroke,
    ]);
    setDebugText(
      describePenDebugStroke(
        stroke,
        strokesRef.current.length,
        canvasRef.current?.clientWidth ?? 0,
      ),
    );
    setDebugCopied("");
  }

  /** 調査用: 直近の線の記録（JSON）を、クリップボードに入れる */
  async function handleDebugCopy() {
    const json = penDebugJson(
      debugStrokesRef.current,
      canvasRef.current?.clientWidth ?? 0,
    );
    const copied = await copyText(json);
    setDebugCopied(copied ? "コピーしました" : "コピーできませんでした");
  }

  function handlePointerEnd(event: ReactPointerEvent<HTMLCanvasElement>) {
    const active = activeRef.current;
    const startedAt = startedAtRef.current;
    if (!active || active.pointerId !== event.pointerId) return;
    if (PEN_DEBUG) finishPenDebugStroke(event.nativeEvent);
    // 離した時刻を最後の点として残す（押したまま止まっていた時間も、書いた時間に入れる）。
    // 離した瞬間の筆圧は、どの入力でも 0 と報告されるので、直前の点の筆圧を使う。
    if (event.type === "pointerup" && startedAt !== null) {
      const { points, drawn } = active.stroke;
      const toLast = (pressure: number) =>
        toPoint(event.nativeEvent, event.currentTarget, startedAt, pressure);
      points.push(toLast(points[points.length - 1].pressure));
      if (drawn !== points) drawn.push(toLast(drawn[drawn.length - 1].pressure));
      pointCountRef.current += 1;
      if (pointCountRef.current >= MAX_POINTS) notifyChange();
    }
    activeRef.current = null;
    // 線の終わりの形を決めて、描き直す
    redraw(canvasRef.current, strokesRef.current);
  }

  const canvas = (
    <canvas
      ref={canvasRef}
      className="writing-canvas"
      role="img"
      aria-label="「と」を書く枠"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerEnd}
      onPointerCancel={handlePointerEnd}
      onLostPointerCapture={handlePointerEnd}
      onContextMenu={(event) => event.preventDefault()}
    />
  );
  // ふだんは枠だけを出す
  if (!PEN_DEBUG) return canvas;
  // 調査用の表示。画面に重ねて置くので、枠やボタンの位置は動かない（index.css の .pen-debug）。
  return (
    <>
      {canvas}
      <div className="pen-debug">
        <button type="button" onClick={handleDebugCopy}>
          直近 3 本の値をコピー（JSON）
        </button>
        <span> {debugCopied}</span>
        <pre>
          {debugText || "ペンの記録: 線を 1 本書くと、ここに値が出ます"}
        </pre>
      </div>
    </>
  );
}

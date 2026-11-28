import { useEffect, useImperativeHandle, useRef } from "react";
import type { PointerEvent as ReactPointerEvent, Ref } from "react";
import { getStroke } from "perfect-freehand";

/** 入力の種類 */
export type PointerType = "mouse" | "touch" | "pen";

/**
 * 画面に描くために覚えておく点。x, y は枠の一辺を 1 とした位置（枠の画素数が
 * 変わっても同じ形で描き直せる）。t は最初の線を書きはじめてからの経過ミリ秒。
 * pressure は筆圧（0〜1）。
 */
type Point = { x: number; y: number; t: number; pressure: number };
/** ポインタを押してから離すまでの 1 本の線。pointerType は書きはじめたときの種類。 */
type Stroke = { pointerType: PointerType; points: Point[] };

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
 * ペンの筆圧をならす時間（ミリ秒）。大きいほど太さの変化がなめらかになるが、
 * 筆圧を変えてから太さが追いつくまでが遅くなる。
 */
const PEN_PRESSURE_SMOOTHING_MS = 80;
/** ならすときに、点 1 個が進めたとみなす最短の時間（ミリ秒） */
const MIN_PRESSURE_STEP_MS = 4;
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
 * ペンの筆圧を、描くためにならす。
 *
 * ペン（Apple Pencil など）で速く書くと、端末が報告する筆圧が、画面の更新 1 回ごとに
 * 上下することがある（1 回の更新でまとめて届く点のうち、新しい点の筆圧が見込みの値で
 * 届くためとみられる）。そのまま太さにすると、線が数珠つなぎのようにくびれる。
 * 手で変える筆圧は、画面の更新（約 17 ミリ秒）よりずっとゆっくり動くので、
 * PEN_PRESSURE_SMOOTHING_MS の時間でならして、細かい上下だけを消す。
 *
 * ならすのは描く太さだけ。記録する筆圧（toRecordedPoint）は、端末が報告した値のまま。
 */
function smoothPenPressures(points: Point[]) {
  // 筆圧 0 は「測れなかった」とみなして使わない（最初の値は、0 でない最初の筆圧）
  let value = points.find((p) => p.pressure > 0)?.pressure ?? 0.5;
  let previousT = points[0].t;
  return points.map((p) => {
    // まとめて届いた点は、時刻が同じことがある。その場合も少しずつ近づける。
    const elapsed = Math.max(MIN_PRESSURE_STEP_MS, p.t - previousT);
    previousT = p.t;
    if (p.pressure > 0) {
      value +=
        (p.pressure - value) *
        (1 - Math.exp(-elapsed / PEN_PRESSURE_SMOOTHING_MS));
    }
    return value;
  });
}

/**
 * 1 本の線の形（ふちをなぞった、塗りつぶす形）を作る。太さは筆圧で変える。
 * ペンは、端末が報告した筆圧を使う。マウスと指は筆圧を測れないので、書く速さから作る
 * （ゆっくりは太く、速いと細い）。記録する筆圧（toRecordedPoint）は、ここでは変えない。
 *
 * @param finished 書き終えた線なら true。書いている途中の線は、終わりの形がまだ決まらない。
 */
function toPath(stroke: Stroke, size: number, finished: boolean) {
  const pen = stroke.pointerType === "pen";
  // ペンの筆圧は、ならしてから使う（理由は smoothPenPressures を参照）
  const pressures = pen ? smoothPenPressures(stroke.points) : null;
  const outline = getStroke(
    stroke.points.map((p, i) => [
      p.x * size,
      p.y * size,
      pressures ? pressures[i] : p.pressure,
    ]),
    {
      ...STROKE_OPTIONS,
      size: size * LINE_WIDTH_RATIO,
      simulatePressure: !pen,
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
    const stroke: Stroke = {
      pointerType,
      points: [
        toPoint(
          native,
          canvas,
          startedAtRef.current,
          toPressure(native, pointerType),
        ),
      ],
    };
    activeRef.current = { pointerId: event.pointerId, stroke };
    strokesRef.current = [...strokesRef.current, stroke];
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
    // 画面の更新より細かく届いた点も使い、速く書いても線が角ばらないようにする
    const native = event.nativeEvent;
    const events = native.getCoalescedEvents?.() ?? [];
    const { pointerType, points } = active.stroke;
    // 上限までの残りの分だけ足す（書いている途中の線があるとき、残りは必ず 1 以上）
    const added = (events.length > 0 ? events : [native])
      .slice(0, MAX_POINTS - pointCountRef.current)
      .map((e) => toPoint(e, canvas, startedAt, toPressure(e, pointerType)));
    points.push(...added);
    pointCountRef.current += added.length;
    // 上限に達したら、押したままでも線をそこで終える
    if (pointCountRef.current >= MAX_POINTS) {
      activeRef.current = null;
      notifyChange();
    }
    redraw(canvas, strokesRef.current, activeRef.current?.stroke);
  }

  function handlePointerEnd(event: ReactPointerEvent<HTMLCanvasElement>) {
    const active = activeRef.current;
    const startedAt = startedAtRef.current;
    if (!active || active.pointerId !== event.pointerId) return;
    // 離した時刻を最後の点として残す（押したまま止まっていた時間も、書いた時間に入れる）。
    // 離した瞬間の筆圧は、どの入力でも 0 と報告されるので、直前の点の筆圧を使う。
    if (event.type === "pointerup" && startedAt !== null) {
      const { points } = active.stroke;
      points.push(
        toPoint(
          event.nativeEvent,
          event.currentTarget,
          startedAt,
          points[points.length - 1].pressure,
        ),
      );
      pointCountRef.current += 1;
      if (pointCountRef.current >= MAX_POINTS) notifyChange();
    }
    activeRef.current = null;
    // 線の終わりの形を決めて、描き直す
    redraw(canvasRef.current, strokesRef.current);
  }

  return (
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
}

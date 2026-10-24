// Отрисовка: облако из n точек в 3D между двумя соседними сценами.
// p — дробный номер сцены (2.4 = 40% пути от сцены 2 к сцене 3).
// Сцена задаёт форму (shape) и вид в 3D: наклон, поворот, покачивание.
import { rng, lerp } from './shapes.js';

const BUCKETS = 16; // точки одного оттенка рисуются одним fill — так быстрее
const DEPTH = [-18, 0, 12]; // дальние точки темнее, ближние светлее
const TAU = Math.PI * 2;
const CAMERA = 3.4; // расстояние до камеры: чем меньше, тем сильнее перспектива
const FLAT = { pitch: 0, yaw: 0, sway: 0 };
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const ease = (t) => t * t * t * (t * (t * 6 - 15) + 10);
const SWAP = 0.9; // секунды на пересборку фигуры при выборе другой задачи

// Доля пути между сценами: у центра секции фигура стоит, перетекает между ними.
export const morphT = (p) => ease(clamp(((p % 1) - 0.15) / 0.7));

export function createStage(canvas, scenes, n, problem) {
  const ctx = canvas.getContext('2d');
  const toBuf = (pts) => {
    const b = new Float32Array(n * 3);
    pts.forEach(([x, y, z = 0], k) => { b[3 * k] = x; b[3 * k + 1] = y; b[3 * k + 2] = z; });
    return b;
  };
  const bufs = scenes.map((s) => toBuf(s.shape(n, problem)));
  const swaps = []; // сцена → { from, at, dur }: старая форма, из которой перетекает новая
  const blends = [];
  const rand = rng(42);
  // Фаза покачивания, направление вихря и собственная глубина точки: пока страница
  // прокручивается, фигура расслаивается по глубине (параллакс), в покое снова плоская.
  const seed = Array.from({ length: n }, () => [rand() * TAU, rand() * 2 - 1, rand() * 2 - 1, (rand() - 0.5) * 0.16]);
  const xs = new Float32Array(n), ys = new Float32Array(n), rs = new Float32Array(n);
  const tier = new Uint8Array(n);
  let dpr = 1, calm = false, push = 0;

  function resize(w, h) {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }

  // Текущая форма сцены i; после пересборки — смесь старой и новой.
  function current(i, time) {
    const sw = swaps[i];
    if (sw && time - sw.at >= sw.dur) swaps[i] = null;
    if (!swaps[i]) return bufs[i];
    const e = ease(clamp((time - sw.at) / sw.dur));
    const out = (blends[i] ||= new Float32Array(n * 3)), src = bufs[i], from = sw.from;
    for (let q = 0; q < 3 * n; q++) out[q] = from[q] + (src[q] - from[q]) * e;
    return out;
  }

  function swapFrom(i, from, time, dur) {
    swaps[i] = { from, at: time, dur };
  }

  // Сцены, зависящие от задачи (shape принимает её вторым аргументом), строятся заново.
  function reshape(next, time) {
    scenes.forEach((s, i) => {
      if (s.shape.length < 2) return;
      const from = current(i, time).slice();
      bufs[i] = toBuf(s.shape(n, next));
      swapFrom(i, from, time, SWAP);
    });
  }

  // Появление: фигура собирается из вращающегося облака, которое больше сцены.
  function intro(time) {
    const cloud = new Float32Array(n * 3);
    for (let k = 0; k < n; k++) {
      const y = 1 - (2 * (k + 0.5)) / n, r = Math.sqrt(1 - y * y), a = k * 2.39996;
      cloud.set([1.5 * r * Math.cos(a), 1.5 * y, 1.5 * r * Math.sin(a)], 3 * k);
    }
    scenes.forEach((_, i) => swapFrom(i, cloud, time, 2.4));
  }

  const swirl = (i, time) => (swaps[i] ? Math.sin(Math.PI * clamp((time - swaps[i].at) / swaps[i].dur)) : 0);
  const yawOf = (v, time) => v.yaw + (calm ? 0 : v.sway * Math.sin(time * 0.32));

  // box — центр и полуразмер фигуры в CSS-пикселях; pointer — курсор над фигурой или null;
  // tilt — добавочный наклон от скорости прокрутки.
  function draw(p, time, box, reduce, pointer, tilt = 0) {
    calm = reduce;
    const i = Math.min(Math.floor(p), scenes.length - 1);
    const j = Math.min(i + 1, scenes.length - 1);
    const t = morphT(p);
    const a = scenes[i], b = scenes[j];
    const A = current(i, time), B = j === i ? A : current(j, time);
    // Сила вихря: 0 в сценах, 1 посередине пути (или посередине пересборки).
    const m = calm ? 0 : Math.max(Math.sin(Math.PI * t), lerp(swirl(i, time), swirl(j, time), t) * 0.6);
    const wob = calm ? 0 : 0.006;
    const rot = m * 0.55, cos = Math.cos(rot), sin = Math.sin(rot), grow = 1 + 0.08 * m;
    const va = a.view || FLAT, vb = b.view || FLAT;
    const layer = Math.min(1, Math.abs(tilt) * 4);
    const pitch = lerp(va.pitch, vb.pitch, t) + tilt, yaw = lerp(yawOf(va, time), yawOf(vb, time), t);
    const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
    const cx0 = box.cx * dpr, cy0 = box.cy * dpr, r = box.r * dpr;
    const base = lerp(a.dot, b.dot, t) * clamp(box.r / 260, 0.7, 1.6) * dpr;

    // Курсор мягко раздвигает точки; сила нарастает и спадает, а не включается рывком.
    push += ((pointer && !calm ? 1 : 0) - push) * 0.08;
    const px = pointer ? pointer.x * dpr : 0, py = pointer ? pointer.y * dpr : 0, reach = 0.22 * r;

    for (let k = 0; k < n; k++) {
      const [ph, nx, ny, nz] = seed[k];
      const q = 3 * k;
      const x = lerp(A[q], B[q], t), y = lerp(A[q + 1], B[q + 1], t), z = lerp(A[q + 2], B[q + 2], t) + nz * layer;
      const x1 = x * cy + z * sy, z1 = z * cy - x * sy;
      const y2 = y * cp - z1 * sp, z2 = y * sp + z1 * cp;
      const s = CAMERA / (CAMERA - z2);
      const u = x1 * s, v = y2 * s;
      let X = cx0 + r * (grow * (u * cos - v * sin) + nx * m * 0.22 + wob * Math.sin(time * 1.3 + ph));
      let Y = cy0 + r * (grow * (u * sin + v * cos) + ny * m * 0.22 + wob * Math.cos(time * 1.1 + ph));
      if (push > 0.01) {
        const dx = X - px, dy = Y - py, d2 = dx * dx + dy * dy + 1;
        const f = (push * reach * reach * reach) / (d2 + reach * reach) / Math.sqrt(d2);
        X += dx * f * 0.35;
        Y += dy * f * 0.35;
      }
      xs[k] = X;
      ys[k] = Y;
      rs[k] = base * s;
      tier[k] = z2 < -0.18 ? 0 : z2 > 0.18 ? 2 : 1;
    }

    const hue = lerp(a.hue, b.hue, t), sat = lerp(a.sat, b.sat, t), light = lerp(a.light, b.light, t);
    const spread = lerp(a.spread, b.spread, t), link = lerp(a.link, b.link, t);

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (link > 0.01) {
      const gap = 0.07 * r;
      ctx.beginPath();
      for (let k = 1; k < n; k++) {
        const near = Math.abs(xs[k] - xs[k - 1]) + Math.abs(ys[k] - ys[k - 1]) < gap;
        if (near) ctx.lineTo(xs[k], ys[k]);
        else ctx.moveTo(xs[k], ys[k]);
      }
      ctx.lineWidth = 1.3 * base;
      ctx.strokeStyle = `hsl(${hue % 360} ${sat}% ${light}% / ${0.7 * link})`;
      ctx.stroke();
    }
    for (let q = 0; q < BUCKETS; q++) {
      const from = Math.floor((q * n) / BUCKETS), to = Math.floor(((q + 1) * n) / BUCKETS);
      const h = (hue + spread * (q / BUCKETS - 0.5)) % 360;
      for (let d = 0; d < 3; d++) {
        ctx.beginPath();
        for (let k = from; k < to; k++) {
          if (tier[k] !== d) continue;
          ctx.moveTo(xs[k] + rs[k], ys[k]);
          ctx.arc(xs[k], ys[k], rs[k], 0, TAU);
        }
        ctx.fillStyle = `hsl(${h} ${sat}% ${light + DEPTH[d]}%)`;
        ctx.fill();
      }
    }
    return [hue % 360, sat, light];
  }

  return { resize, draw, reshape, intro };
}

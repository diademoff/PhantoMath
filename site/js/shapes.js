// Генераторы облаков точек. Все фигуры живут в единичном квадрате [-1, 1]², y вниз.

const S = 512; // размер холста, на котором рисуются фигуры перед выборкой
export const MATH = '"STIX Two Text", "Cambria Math", "Times New Roman", serif';

// Детерминированный ГПСЧ: одна и та же раскладка точек при каждой загрузке.
export function rng(seed) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const toUnit = (v) => (v / S) * 2 - 1;

// Рисует фигуру белым на скрытом холсте и берёт n случайных закрашенных пикселей.
export function sample(draw, n, seed = 1) {
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.fillStyle = ctx.strokeStyle = '#fff';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.lineCap = ctx.lineJoin = 'round';
  draw(ctx);
  const data = ctx.getImageData(0, 0, S, S).data;
  const filled = [];
  for (let i = 3; i < data.length; i += 4) if (data[i] > 128) filled.push((i - 3) / 4);
  const rand = rng(seed);
  const pts = [];
  for (let k = 0; k < n; k++) {
    const p = filled[Math.floor(rand() * filled.length)] ?? 0;
    pts.push([toUnit((p % S) + rand()), toUnit(Math.floor(p / S) + rand())]);
  }
  // Сортировка слева направо: соседние сцены перетекают волной, а не взрывом.
  return pts.sort((a, b) => a[0] - b[0]);
}

// Текст, ужатый по ширине в рамку w.
export function text(ctx, str, x, y, size, w = 470, style = 'italic') {
  ctx.font = `${style} ${size}px ${MATH}`;
  const k = Math.min(1, w / ctx.measureText(str).width);
  ctx.font = `${style} ${size * k}px ${MATH}`;
  ctx.fillText(str, x, y);
}

// Ломаная из параметрических кривых: точки идут подряд, поэтому их можно соединить линией.
export function curves(parts, n) {
  const pts = [];
  parts.forEach(([share, f], j) => {
    const m = j === parts.length - 1 ? n - pts.length : Math.round(n * share);
    for (let i = 0; i < m; i++) pts.push(f(i / (m - 1 || 1)));
  });
  return pts;
}

export const lerp = (a, b, t) => a + (b - a) * t;

// Сцены по порядку секций страницы: форма, «тип» (точки ↔ линии), цвет и вид в 3D.
// hue растёт монотонно и делает полный круг: последняя сцена снова фирменная малиновая.
import { sample, text, curves, lerp, rng, MATH } from './shapes.js';

const u = (v) => (v / 512) * 2 - 1;

// Задачи для «живого» примера: по ним пересобираются уравнение, шаги и график.
export const PROBLEMS = [
  { eq: 'x² − 5x + 6 = 0', factored: '(x − 2)(x − 3) = 0', roots: [2, 3], b: -5, c: 6 },
  { eq: 'x² − 2x − 8 = 0', factored: '(x + 2)(x − 4) = 0', roots: [-2, 4], b: -2, c: -8 },
  { eq: 'x² − 6x + 9 = 0', factored: '(x − 3)² = 0', roots: [3], b: -6, c: 9 },
];
export const answer = (p) => p.roots.map((r) => `x = ${String(r).replace('-', '−')}`).join(',  ');

function logo(ctx) {
  ctx.lineWidth = 28;
  ctx.beginPath();
  ctx.moveTo(370, 150);
  ctx.lineTo(370, 94);
  ctx.lineTo(142, 94);
  ctx.lineTo(142, 410);
  ctx.lineTo(370, 410);
  ctx.lineTo(370, 354);
  ctx.stroke();
  text(ctx, 'π', 250, 255, 230);
  ctx.font = `700 64px ${MATH}`;
  ctx.fillText('+', 372, 192);
  ctx.fillText('−', 372, 250);
  ctx.fillText('×', 372, 306);
}

function bulb(ctx) {
  ctx.lineWidth = 22;
  ctx.beginPath();
  ctx.arc(256, 200, 120, Math.PI * 0.78, Math.PI * 2.22);
  ctx.lineTo(312, 372);
  ctx.lineTo(200, 372);
  ctx.closePath();
  ctx.stroke();
  ctx.fillRect(206, 398, 100, 20);
  ctx.fillRect(222, 432, 68, 20);
  text(ctx, '?', 256, 212, 170, 470, 'normal');
}

// Логотип с толщиной: точки разнесены по глубине, и при покачивании он выглядит объёмным.
function logo3d(n, seed) {
  const r = rng(seed + 100);
  return sample(logo, n, seed).map(([x, y]) => [x, y, (r() - 0.5) * 0.18]);
}

// Экран телефона в единичных координатах: сюда main.js кладёт скриншоты.
export const SCREEN = { x0: u(158), y0: u(36), x1: u(354), y1: u(476) };

function phone(ctx) {
  ctx.lineWidth = 8;
  ctx.beginPath();
  ctx.roundRect(146, 20, 220, 472, 34);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(256, 28, 4, 0, Math.PI * 2);
  ctx.fill();
}

// Три пути решения из одной задачи: ветка заканчивается кружком-ответом.
function methods(n) {
  const ends = [-0.6, 0, 0.6];
  const s = (t) => t * t * (3 - 2 * t);
  return curves(
    ends.flatMap((y) => [
      [0.25, (t) => [lerp(-0.85, 0.62, t), y * s(t)]],
      [0.083, (t) => [0.74 - 0.12 * Math.cos(t * Math.PI * 2), y + 0.12 * Math.sin(t * Math.PI * 2)]],
    ]),
    n,
  );
}

// График y = x² + bx + c: окно вокруг вершины и корней, ось y видна всегда.
function graph(n, { b, c, roots }) {
  const f = (x) => x * x + b * x + c;
  const h = -b / 2;
  const w = Math.max(2.5, (Math.max(...roots) - Math.min(...roots)) / 2 + 1.5);
  const x0 = Math.min(h - w, -0.4), x1 = Math.max(h + w, 0.4);
  const lo = Math.min(f(h), 0), hi = Math.max(f(x0), f(x1));
  const X = (x) => ((2 * (x - x0)) / (x1 - x0) - 1) * 0.85;
  const Y = (y) => 0.8 - (1.6 * (y - lo)) / (hi - lo);
  return curves(
    [
      [0.16, (t) => [lerp(-0.95, 0.95, t), Y(0)]],
      [0.12, (t) => [X(0), lerp(0.95, -0.95, t)]],
      [0.72, (t) => { const x = lerp(x0, x1, t); return [X(x), Y(f(x))]; }],
    ],
    n,
  );
}

// Сцены 1, 2 и 5 зависят от выбранной задачи: (n, задача) → точки.
export const SCENES = [
  { hue: 348, sat: 85, light: 58, spread: 18, dot: 1.5, link: 0, view: { pitch: 0.12, yaw: 0, sway: 0.42 },
    shape: (n) => logo3d(n, 1) },
  { hue: 382, sat: 90, light: 60, spread: 24, dot: 1.4, link: 0,
    shape: (n, p) => sample((c) => text(c, p.eq, 256, 256, 110), n, 2) },
  { hue: 402, sat: 90, light: 60, spread: 20, dot: 1.2, link: 0,
    shape: (n, p) => sample((c) => {
      text(c, p.eq, 256, 140, 66, 420);
      text(c, p.factored, 256, 256, 66, 420);
      text(c, answer(p), 256, 372, 66, 420);
    }, n, 3) },
  { hue: 418, sat: 95, light: 62, spread: 16, dot: 1.4, link: 0, shape: (n) => sample(bulb, n, 4) },
  { hue: 520, sat: 75, light: 56, spread: 30, dot: 1.1, link: 1, shape: methods },
  { hue: 552, sat: 85, light: 60, spread: 30, dot: 1.0, link: 1, shape: graph },
  { hue: 610, sat: 80, light: 66, spread: 110, dot: 1.3, link: 0,
    shape: (n) => sample((c) => {
      text(c, '∫', 120, 150, 190);
      text(c, 'Σ', 300, 120, 130, 470, 'normal');
      text(c, '√x', 420, 230, 110);
      text(c, 'π', 250, 270, 150);
      text(c, 'lim', 110, 370, 90);
      text(c, '∞', 300, 420, 120, 470, 'normal');
      text(c, 'det', 430, 400, 80);
    }, n, 6) },
  { hue: 650, sat: 70, light: 64, spread: 40, dot: 1.0, link: 0, screen: true, shape: (n) => sample(phone, n, 7) },
  { hue: 680, sat: 80, light: 62, spread: 40, dot: 1.4, link: 0,
    shape: (n) => sample((c) => {
      text(c, 'Aa', 256, 160, 150, 470, 'normal');
      text(c, '⇄', 256, 262, 80, 470, 'normal');
      text(c, 'Яя', 256, 370, 150, 470, 'normal');
    }, n, 8) },
  { hue: 708, sat: 85, light: 58, spread: 18, dot: 1.5, link: 0, view: { pitch: 0.12, yaw: 0, sway: 0.42 },
    shape: (n) => logo3d(n, 9) },
];

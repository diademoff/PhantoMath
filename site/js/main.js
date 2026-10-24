import { SCENES, SCREEN, PROBLEMS, answer } from './scenes.js';
import { createStage } from './morph.js';
import { initLang } from './i18n.js';
import { createDepth } from './depth.js';
import { smoothScroll } from './scroll.js';

initLang();

// Скрытое начальное состояние только при работающем модуле: без него текст виден сразу.
document.documentElement.classList.add('js');

// Появление: заголовок, текст и остальное поднимаются по очереди, один раз.
const sections = [...document.querySelectorAll('[data-scene]')];
const seen = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { e.target.classList.add('in'); seen.unobserve(e.target); }
}, { threshold: 0.3 });
for (const s of sections) {
  [...s.querySelector('.card').children].forEach((c, i) => c.style.setProperty('--i', i));
  seen.observe(s);
}

// Фигуры рисуются шрифтом, поэтому ждём его (но не дольше 3 с — дальше системный serif).
await Promise.race([
  Promise.all(['italic 100px "STIX Two Text"', '100px "STIX Two Text"', '700 100px "STIX Two Text"']
    .map((f) => document.fonts.load(f))).catch(() => {}),
  new Promise((r) => setTimeout(r, 3000)),
]);

const canvas = document.getElementById('stage');
const figure = document.querySelector('.figure');
const screen = document.querySelector('.screen');
const shots = [...screen.querySelectorAll('img')];
const root = document.documentElement;
const calm = matchMedia('(prefers-reduced-motion: reduce)');
const PHONE = SCENES.findIndex((s) => s.screen);
const stage = createStage(canvas, SCENES, innerWidth < 700 ? 1000 : 1600, PROBLEMS[0]);
const depth = createDepth(document.getElementById('depth'));
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));

// focus — высота «линии чтения»: середина части экрана, где виден текст (на телефоне — под фигурой).
// under — нижний край фигуры на телефоне: выше него текст растворяется (0 на широком экране).
let H, focus, mids, stops, box, under;
function layout() {
  H = innerHeight;
  depth.resize(innerWidth, H);
  const p = figure.getBoundingClientRect(), c = canvas.getBoundingClientRect();
  // Фигура вписана в своё место; холст больше него, поэтому центр смещён на разницу.
  stage.resize(c.width, c.height);
  const r = (Math.min(p.width, p.height) / 2) * 0.84;
  box = { cx: p.left - c.left + p.width / 2, cy: p.top - c.top + p.height / 2, r };
  Object.assign(screen.style, {
    left: `${p.width / 2 + SCREEN.x0 * r}px`,
    top: `${p.height / 2 + SCREEN.y0 * r}px`,
    width: `${(SCREEN.x1 - SCREEN.x0) * r}px`,
    height: `${(SCREEN.y1 - SCREEN.y0) * r}px`,
  });
  const narrow = p.width > innerWidth / 2;
  focus = narrow ? (p.bottom + H) / 2 : H / 2;
  under = narrow ? p.bottom : 0;
  mids = sections.map((s) => s.offsetTop + s.offsetHeight / 2);
  // Крайние сцены должны достигаться даже там, где страница дальше не прокручивается.
  const end = document.documentElement.scrollHeight - (H - focus);
  stops = mids.map((m) => Math.min(Math.max(m, focus), end));
}

// Дробный номер сцены по положению середины экрана между серединами секций.
function goal() {
  const vc = scrollY + focus;
  if (vc <= stops[0]) return 0;
  for (let i = 0; i < stops.length - 1; i++) {
    if (vc < stops[i + 1]) return i + (vc - stops[i]) / (stops[i + 1] - stops[i]);
  }
  return stops.length - 1;
}

const smooth = smoothScroll(() => stops.map((s) => s - focus), calm);

let shown = 0, tilt = 0;
let before = performance.now();
function frame(now) {
  const dt = Math.min(0.1, (now - before) / 1000);
  before = now;
  smooth(dt);
  // Фигура догоняет прокрутку плавно: даже прыжок через всю страницу идёт без рывка.
  const was = shown;
  shown += (goal() - shown) * (1 - Math.exp(-dt * 4));
  // Параллакс фигуры: на ходу она наклоняется по направлению прокрутки и расслаивается по глубине.
  const lean = calm.matches || dt === 0 ? 0 : clamp(((shown - was) / dt) * 0.3, -0.3, 0.3);
  tilt += (lean - tilt) * (1 - Math.exp(-dt * 5));
  // Цвет фигуры перекрашивает и страницу: фон и акцент — плоскими заливками.
  const [h, s, l] = stage.draw(shown, now / 1000, box, calm.matches, pointer, tilt);
  depth.draw(calm.matches ? 0 : scrollY, h);
  root.style.setProperty('--accent', `hsl(${h} ${s}% ${l}%)`);
  root.style.setProperty('--ground', `hsl(${h} 30% 6%)`);
  root.style.setProperty('--tone', `hsl(${h} 28% 16%)`);
  const vc = scrollY + focus;
  sections.forEach((s, i) => {
    s.style.setProperty('--vis', clamp(1.3 - (2 * Math.abs(mids[i] - vc)) / H).toFixed(3));
    // Параллакс текста: --d от −1 до 1 — где секция относительно линии чтения.
    s.style.setProperty('--d', calm.matches ? 0 : clamp((mids[i] - vc) / H, -1, 1).toFixed(3));
    if (under) s.style.setProperty('--cut', `${under - s.getBoundingClientRect().top}px`);
  });
  screen.style.opacity = clamp(1 - Math.abs(shown - PHONE) * 3.5).toFixed(3);
  requestAnimationFrame(frame);
}

// Скриншоты на экране телефона сменяют друг друга (переход — CSS opacity).
let shot = 0;
setInterval(() => {
  if (screen.style.opacity === '0.000') return;
  shots[shot].classList.remove('on');
  shot = (shot + 1) % shots.length;
  shots[shot].classList.add('on');
}, 3000);

// Живой пример: выбор задачи пересобирает уравнение, шаги и график.
const out = document.getElementById('answer');
const group = document.querySelector('.problems');
PROBLEMS.forEach((p, i) => {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'math';
  b.textContent = p.eq;
  b.setAttribute('aria-pressed', String(i === 0));
  b.addEventListener('click', () => {
    for (const o of group.children) o.setAttribute('aria-pressed', String(o === b));
    out.textContent = answer(p);
    stage.reshape(p, performance.now() / 1000);
  });
  group.append(b);
});

// Курсор над фигурой мягко раздвигает точки.
let pointer = null;
figure.addEventListener('pointermove', (e) => {
  const r = canvas.getBoundingClientRect();
  pointer = { x: e.clientX - r.left, y: e.clientY - r.top };
});
figure.addEventListener('pointerleave', () => { pointer = null; });

layout();
shown = goal();
if (!calm.matches) stage.intro(performance.now() / 1000);
addEventListener('resize', layout);
const resized = new ResizeObserver(layout);
resized.observe(document.querySelector('main'));
resized.observe(figure);
requestAnimationFrame(frame);

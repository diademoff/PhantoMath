// Фон с параллаксом: бледные математические знаки в трёх слоях глубины.
// Дальний слой едет медленнее прокрутки, ближний быстрее — экран получает глубину.
import { rng, MATH } from './shapes.js';

const GLYPHS = ['+', '−', '×', '÷', '=', 'π', '√', 'Σ', '∫', '∞', 'x²', 'dx', 'Δ', 'θ', '≤', 'e', 'f(x)', '½'];
const LAYERS = [
  { speed: 0.12, size: 15, alpha: 0.07 },
  { speed: 0.3, size: 24, alpha: 0.1 },
  { speed: 0.55, size: 38, alpha: 0.13 },
];
const PAD = 80; // знак уходит за край целиком, прежде чем появиться с другой стороны

export function createDepth(canvas) {
  const ctx = canvas.getContext('2d');
  const r = rng(7);
  let items = [], dpr = 1, W = 0, H = 0;

  function resize(w, h) {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = w;
    H = h;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    const per = Math.round((w * h) / 52000); // плотность не зависит от размера экрана
    items = LAYERS.flatMap((layer) => Array.from({ length: per }, () => ({
      layer,
      x: r() * w,
      y: r() * (h + 2 * PAD),
      glyph: GLYPHS[Math.floor(r() * GLYPHS.length)],
      tilt: (r() - 0.5) * 0.5,
    })));
  }

  function draw(scroll, hue) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const span = H + 2 * PAD;
    for (const { layer, x, y, glyph, tilt } of items) {
      const yy = ((((y - scroll * layer.speed) % span) + span) % span) - PAD;
      ctx.font = `italic ${layer.size}px ${MATH}`;
      ctx.fillStyle = `hsl(${hue} 60% 78% / ${layer.alpha})`;
      ctx.save();
      ctx.translate(x, yy);
      ctx.rotate(tilt);
      ctx.fillText(glyph, 0, 0);
      ctx.restore();
    }
  }

  return { resize, draw };
}

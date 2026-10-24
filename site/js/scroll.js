// Плавная прокрутка колесом мыши: страница догоняет цель с инерцией, а остановившись
// незадолго до середины следующей секции, мягко доезжает до неё (только вперёд, назад не тянет). Тачпады шлют те же события wheel;
// касания, клавиатура, полоса прокрутки и якоря остаются родными — цель под них подстраивается.
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const MAGNET = 0.3; // доля высоты экрана, в которой срабатывает доводка
const IDLE = 0.18; // секунды без колеса, после которых — доводка

// snaps() — положения scrollY, в которых сцена стоит ровно; calm — prefers-reduced-motion.
export function smoothScroll(snaps, calm) {
  let target = scrollY, ours = scrollY, active = false, idle = 0, settled = true, dir = 1;
  const max = () => document.documentElement.scrollHeight - innerHeight;

  addEventListener('wheel', (e) => {
    if (calm.matches || e.ctrlKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
    e.preventDefault();
    const unit = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? innerHeight : 1;
    if (!active) target = ours = scrollY;
    target = clamp(target + e.deltaY * unit, 0, max());
    dir = Math.sign(e.deltaY) || dir;
    active = true;
    idle = 0;
    settled = false;
  }, { passive: false });

  // Прокрутка не от нас (клавиши, полоса, якорь, касание): принимаем её как новую точку отсчёта.
  addEventListener('scroll', () => {
    if (Math.abs(scrollY - ours) > 2) {
      target = ours = scrollY;
      active = false;
    }
  });

  return function step(dt) {
    if (!active) return;
    idle += dt;
    if (!settled && idle > IDLE) {
      settled = true;
      const ahead = snaps().filter((s) => (s - target) * dir >= 0 && Math.abs(s - target) < innerHeight * MAGNET);
      if (ahead.length) target = clamp(dir > 0 ? Math.min(...ahead) : Math.max(...ahead), 0, max());
    }
    ours += (target - ours) * (1 - Math.exp(-dt * 8));
    if (Math.abs(target - ours) < 0.5 && settled) {
      ours = target;
      active = false;
    }
    window.scrollTo({ top: ours, behavior: 'instant' });
  };
}

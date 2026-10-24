// Русский текст лежит прямо в index.html, здесь — только английский.
const EN = {
  title: 'PhantoMath — solves and explains every step',
  p0: 'A maths solver for Android. It shows every step and explains why it is allowed. Offline, free and open source.',
  b0: 'Source code on GitHub',
  b1: 'See what it does',
  h1: 'The answer appears as you type',
  p1: 'There is no Solve button. Fractions, powers and roots go into their own slots, and the answer is ready the '
    + 'moment the problem is complete. Pick a problem and the figure rebuilds itself:',
  g1: 'Problem',
  a1: 'Answer:',
  h2: 'Every step on its own card',
  p2: 'The formula before and after, and one sentence on what was done. Need more? Open the step and go all the '
    + 'way down to column arithmetic.',
  h3: '“Why?” on every rule',
  p3: 'A short theory article: the rule, its formula, when it applies, a worked example and the typical mistake.',
  h4: 'Several ways to solve',
  p4: 'A quadratic equation is solved by factoring, by the formula or by completing the square. Switch between '
    + 'methods and compare.',
  h5: 'The roots, on a graph',
  p5: 'Domain, zeros, extrema and asymptotes, with an interactive graph of the function beside them. '
    + 'The roots sit right on the axis.',
  h6: 'From fractions to calculus',
  p6: 'School maths and the first years of university:',
  t6: ['Arithmetic', 'Algebra', 'Equations', 'Inequalities', 'Systems', 'Trigonometry', 'Functions', 'Limits',
    'Derivatives', 'Integrals', 'Series', 'Matrices & vectors', 'Complex numbers', 'Combinatorics',
    'Conic sections', 'Differential equations'].map((t) => `<li>${t}</li>`).join(''),
  h7: 'Solved right on the phone',
  p7: 'The Python and SymPy solver runs on the device. No account, no ads, no subscription. Your homework never '
    + 'leaves the phone.',
  h8: 'English and Russian',
  p8: 'The whole interface and every explanation in two languages. Switch in the settings.',
  h9: 'Open source, GPL-3.0',
  p9: 'See how each step is produced, fix it and add topics. Over 1800 tests check the answers. To build the APK:',
  b9: 'Open on GitHub',
  c9: 'What the build needs',
  f1: 'How it works',
  f2: 'Contributing',
  f3: 'License',
  d1: 'tests check the answers',
  d2: 'areas of mathematics',
  d3: 'languages of explanation',
  d4: 'ads and tracking',
  n1: 'Features',
};

export function initLang() {
  const nodes = [...document.querySelectorAll('[data-i18n]')];
  const labels = [...document.querySelectorAll('[data-i18n-label]')];
  const ru = new Map([...nodes.map((n) => [n, n.innerHTML]), ...labels.map((n) => [n, n.getAttribute('aria-label')])]);
  const btn = document.getElementById('lang');
  let lang;
  try { lang = localStorage.getItem('lang'); } catch { /* приватный режим */ }
  lang ||= navigator.language.startsWith('ru') ? 'ru' : 'en';

  const apply = () => {
    const en = lang === 'en';
    for (const n of nodes) n.innerHTML = en ? EN[n.dataset.i18n] : ru.get(n);
    for (const n of labels) n.setAttribute('aria-label', en ? EN[n.dataset.i18nLabel] : ru.get(n));
    document.documentElement.lang = lang;
    btn.textContent = en ? 'RU' : 'EN';
    btn.setAttribute('aria-label', en ? 'Переключить на русский' : 'Switch to English');
    for (const img of document.querySelectorAll('[data-shot]')) img.src = `screenshots/${lang}-${img.dataset.shot}.png`;
    try { localStorage.setItem('lang', lang); } catch { /* приватный режим */ }
  };
  btn.addEventListener('click', () => { lang = lang === 'en' ? 'ru' : 'en'; apply(); });
  apply();
}

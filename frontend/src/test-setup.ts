// jsdom, <canvas> 2D bağlamını UYGULAMAZ (`getContext('2d')` null döner ve
// konsola "Not implemented" basar). Kokpit bileşeni monte olurken gerçek bir
// canvas bağlamı üzerinde fizik adımı çalıştırıyor; testte yalnız çağrılan
// yüzeyi karşılayan bir yer tutucu veriyoruz. Çizim doğrulanmıyor — testin
// konusu API sözleşmesi.
const noop = () => {};

const ctxStub = {
  canvas: null as unknown,
  save: noop,
  restore: noop,
  clearRect: noop,
  beginPath: noop,
  closePath: noop,
  arc: noop,
  moveTo: noop,
  lineTo: noop,
  fill: noop,
  stroke: noop,
  fillText: noop,
  measureText: () => ({ width: 10 }),
  createLinearGradient: () => ({ addColorStop: noop }),
  setTransform: noop,
  translate: noop,
  scale: noop,
  fillStyle: '',
  strokeStyle: '',
  lineWidth: 1,
  font: '',
  textAlign: 'center',
  shadowBlur: 0,
  shadowColor: '',
  globalAlpha: 1,
};

Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
  configurable: true,
  writable: true,
  value: () => ctxStub,
});

// jsdom'da requestAnimationFrame var; yine de bileşen kapanırken döngü
// sızmasın diye tek kareye indiriyoruz.
globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) =>
  setTimeout(() => cb(performance.now()), 0) as unknown as number) as typeof requestAnimationFrame;
globalThis.cancelAnimationFrame = ((id: number) => clearTimeout(id)) as typeof cancelAnimationFrame;

// Bileşen `import.meta.env` okuyor.
(import.meta as any).env = (import.meta as any).env || {};

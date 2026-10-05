/**
 * PINEAL-HERETIC v5.0 - Organik Iris Renderer
 * Yüksek çözünürlüklü organik irisi merkeze yerleştirip,
 * fare imlecini mikro düzeyde takip eden, sistem veri işlerken
 * hafifçe nefes alan/genişleyen Canvas optik katmanı.
 */

export interface IrisRendererOptions {
  irisImageSrc: string;
  size: number;
  mouseSensitivity?: number;
  breathingSpeed?: number;
  breathingAmplitude?: number;
}

export class IrisRenderer {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private irisImage: HTMLImageElement | null = null;
  private imageLoaded = false;
  private rafId = 0;
  private alive = false;

  // Mouse tracking
  private targetX = 0;
  private targetY = 0;
  private currentX = 0;
  private currentY = 0;
  private mouseNormX = 0;
  private mouseNormY = 0;

  // Breathing
  private scale = 1.0;
  private startTime = 0;
  private isProcessing = false;
  private processingIntensity = 0;

  // [FAZ C · C3] Göz DİNLER ve SUSAR: dinlerken gözbebeği BÜYÜR,
  // konuşurken iris hafif titrer. Durum backend'den gelir (uydurma yok).
  private isListening = false;
  private isSpeaking = false;
  private listenAmount = 0;

  // Organic drift
  private driftX = 0;
  private driftY = 0;

  private options: Required<IrisRendererOptions>;

  constructor(canvas: HTMLCanvasElement, opts: IrisRendererOptions) {
    this.canvas = canvas;
    const ctx = canvas.getContext('2d', { alpha: true, desynchronized: true });
    if (!ctx) throw new Error('Canvas 2D context alinamadi');
    this.ctx = ctx;
    this.options = {
      mouseSensitivity: 4.5,
      breathingSpeed: 0.5,
      breathingAmplitude: 0.012,
      ...opts,
    };
    this.setupCanvas();
    this.loadImage(opts.irisImageSrc);
  }

  private setupCanvas() {
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
    const rect = this.canvas.getBoundingClientRect();
    const size = this.options.size || rect.width || 400;
    this.canvas.width = size * dpr;
    this.canvas.height = size * dpr;
    this.canvas.style.width = `${size}px`;
    this.canvas.style.height = `${size}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // GPU hint
    this.canvas.style.transform = 'translateZ(0)';
    this.canvas.style.willChange = 'transform';
  }

  private loadImage(src: string) {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      this.irisImage = img;
      this.imageLoaded = true;
    };
    img.onerror = () => {
      console.warn('Iris image yuklenemedi:', src);
      this.imageLoaded = false;
    };
    img.src = src;
  }

  public setMousePosition(clientX: number, clientY: number) {
    if (typeof window === 'undefined') return;
    const width = window.innerWidth;
    const height = window.innerHeight;
    const normX = (clientX - width / 2) / (width / 2);
    const normY = (clientY - height / 2) / (height / 2);
    this.mouseNormX = Math.max(-1, Math.min(1, normX));
    this.mouseNormY = Math.max(-1, Math.min(1, normY));
    this.targetX = this.mouseNormX * this.options.mouseSensitivity;
    this.targetY = this.mouseNormY * (this.options.mouseSensitivity * 0.78);
  }

  public setProcessing(active: boolean, intensity = 0.6) {
    this.isProcessing = active;
    this.processingIntensity = intensity;
  }

  /** Dinleme: gözbebeği yavaşça büyür (karşısındakini duyan göz). */
  public setListening(active: boolean) {
    this.isListening = active;
  }

  /** Konuşma: iris hafif titrer (canlı varlık). */
  public setSpeaking(active: boolean) {
    this.isSpeaking = active;
  }

  public start() {
    if (this.alive) return;
    this.alive = true;
    this.startTime = performance.now();
    this.loop(performance.now());
  }

  public stop() {
    this.alive = false;
    if (this.rafId) cancelAnimationFrame(this.rafId);
  }

  public resize(size: number) {
    this.options.size = size;
    this.setupCanvas();
  }

  private loop = (t: number) => {
    if (!this.alive) return;
    const elapsed = (t - this.startTime) * 0.001;

    // Organic drift - 2 sinus frekansi
    const organicDriftX = Math.sin(elapsed * 0.45) * 2.2 + Math.sin(elapsed * 0.18) * 1.0;
    const organicDriftY = Math.cos(elapsed * 0.35) * 1.8 + Math.cos(elapsed * 0.12) * 0.8;

    // Processing flutter
    const processingFlutter = this.isProcessing ? Math.sin(elapsed * 3.5) * this.processingIntensity : 0;

    // [FAZ C · C3] Dinleme yumuşak geçişle açılır/kapanır (ani zıplama yok).
    const listenTarget = this.isListening ? 1 : 0;
    this.listenAmount += (listenTarget - this.listenAmount) * 0.06;
    // Konuşurken iris titrer: küçük, canlı bir salınım.
    const speakTremble = this.isSpeaking ? Math.sin(elapsed * 6.5) * 0.9 : 0;

    const desiredX = this.targetX + organicDriftX + processingFlutter + speakTremble;
    const desiredY = this.targetY + organicDriftY + speakTremble * 0.4;

    // Lerp 0.04 - yavas ve kaliteli akis
    this.currentX += (desiredX - this.currentX) * 0.04;
    this.currentY += (desiredY - this.currentY) * 0.04;

    // Breathing scale
    const baseBreath = Math.sin(elapsed * this.options.breathingSpeed) * this.options.breathingAmplitude;
    const procBreath = this.isProcessing ? Math.sin(elapsed * 2.2) * 0.008 : 0;
    this.scale = 1.016 + baseBreath + procBreath;

    this.render(elapsed);

    this.rafId = requestAnimationFrame(this.loop);
  };

  private render(elapsed: number) {
    const ctx = this.ctx;
    const size = this.options.size;
    const center = size / 2;
    const irisRadius = size * 0.42;

    ctx.clearRect(0, 0, size, size);

    // Save
    ctx.save();
    ctx.translate(center + this.currentX, center + this.currentY);
    ctx.scale(this.scale, this.scale);

    // Clip circle - iris yuvasi
    ctx.beginPath();
    ctx.arc(0, 0, irisRadius, 0, Math.PI * 2);
    ctx.clip();

    // Iris image
    if (this.imageLoaded && this.irisImage) {
      const imgSize = irisRadius * 2.16;
      ctx.drawImage(this.irisImage, -imgSize / 2, -imgSize / 2, imgSize, imgSize);
      // Contrast boost
      ctx.globalCompositeOperation = 'overlay';
      ctx.fillStyle = `rgba(212, 175, 55, ${0.08 + Math.sin(elapsed * 0.3) * 0.03})`;
      ctx.fillRect(-imgSize / 2, -imgSize / 2, imgSize, imgSize);
      ctx.globalCompositeOperation = 'source-over';
    } else {
      // Fallback procedural iris
      const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, irisRadius);
      grad.addColorStop(0, '#0a0502');
      grad.addColorStop(0.15, '#1c0d03');
      grad.addColorStop(0.24, '#5a2f0c');
      grad.addColorStop(0.36, '#a86f1d');
      grad.addColorStop(0.48, '#e9c25c');
      grad.addColorStop(0.6, '#7a4d12');
      grad.addColorStop(0.74, '#2a1505');
      grad.addColorStop(1, '#000');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(0, 0, irisRadius, 0, Math.PI * 2);
      ctx.fill();
    }

    // Pupil - nefes alir
    const pupilBase = irisRadius * 0.36;
    const pupilPulse = this.isProcessing ? Math.sin(elapsed * 1.8) * 0.12 + 0.88 : 1 + Math.sin(elapsed * 0.5) * 0.05;
    // Dinlerken gözbebeği %22'ye kadar BÜYÜR (odak = karşısındaki insan).
    const pupilSize = pupilBase * pupilPulse * (1 + this.listenAmount * 0.22);
    const pupilGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, pupilSize);
    pupilGrad.addColorStop(0, '#1a1a1a');
    pupilGrad.addColorStop(0.46, '#000');
    pupilGrad.addColorStop(1, '#000');
    ctx.fillStyle = pupilGrad;
    ctx.beginPath();
    ctx.arc(0, 0, pupilSize, 0, Math.PI * 2);
    ctx.fill();

    // Glint
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.beginPath();
    ctx.ellipse(-irisRadius * 0.28, -irisRadius * 0.32, irisRadius * 0.12, irisRadius * 0.08, -0.3, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();

    // Outer shadow / depth
    ctx.save();
    ctx.beginPath();
    ctx.arc(center, center, irisRadius, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(0,0,0,0.9)';
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.restore();
  }

  public destroy() {
    this.stop();
    this.irisImage = null;
  }
}

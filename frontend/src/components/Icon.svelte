<!--
  Icon.svelte — tek noktadan ikon katmanı.

  Neden var: kokpit, ✦ ◈ ▲ ⌖ ⟐ ◬ ⟡ ⯁ ◇ ◆ ✷ ◉ ↻ ⟳ ⬇ ⚠ ⛔ 🔑 📡 📱 🔥 ⚙ 🔒 📜 📄 ⏱
  gibi glifleri metin olarak basıyordu. Ölçüldü (fontTools, JetBrains Mono cmap):
  bu gliflerin 30'dan fazlası fontta YOK ve tarayıcıda kutu (tofu) ya da boşluk
  olarak görünüyor. Aynı glifler modal kapatma düğmesinde de kullanılıyordu.

  Bu bileşen her ikonu currentColor ile çizen satır içi SVG üretir; font
  bağımlılığı yok, tofu riski yok, temas rengini otomatik alır.
-->
<script lang="ts">
  // 24x24 viewBox, stroke tabanlı (feather çizgisi). `size` em cinsinden.
  export let name: string = 'sparkle';
  export let size: number = 1;
  export let label: string = ''; // boşsa aria-hidden (dekoratif)

  const PATHS: Record<string, string> = {
    sparkle: 'M12 2l2.2 6.3L21 10.5l-6.8 2.2L12 19l-2.2-6.3L3 10.5l6.8-2.2z',
    diamond: 'M12 2l8 10-8 10-8-10z',
    dot: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
    target: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2z',
    layers: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5',
    'triangle-up': 'M12 5l9 14H3z',
    'triangle-down': 'M5 7l7 11 7-11z',
    refresh: 'M20.5 12a8.5 8.5 0 1 1-2.5-6M21 4v5h-5',
    square: 'M5 5h14v14H5z',
    'circle-hollow': 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16z',
    hexagon: 'M12 2l8.7 5v10L12 22l-8.7-5V7z',
    star: 'M12 2.5l2.9 6.2 6.6.9-4.8 4.7 1.2 6.6L12 17.7 6.1 20.9l1.2-6.6L2.5 9.6l6.6-.9z',
    clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3.5 2',
    eye: 'M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
    close: 'M6 6l12 12M18 6L6 18',
    'chevron-up': 'M6 15l6-6 6 6',
    'chevron-down': 'M6 9l6 6 6-6',
    warning: 'M12 3l10 18H2zM12 10v4M12 17.2v.3',
    stop: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM8.5 8.5l7 7M15.5 8.5l-7 7',
    key: 'M14.5 9a4 4 0 1 0-7.7 1.6L3 14.4V20h5.6l1.4-1.4v-2.2h2.2l1.2-1.2A4 4 0 0 0 14.5 9z',
    satellite: 'M4 10a8 8 0 0 1 14 5M8 6a12 12 0 0 1 10 10M12 12l6 6M3 21l4-4',
    phone: 'M8 2h8a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM11 18h2',
    flame: 'M12 2s5 4.5 5 9a5 5 0 0 1-10 0c0-2 1-3.5 2-4.5 0 1.5.6 2.5 1.5 3 0-2.5 1-5.5 1.5-7.5z',
    gear: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1',
    lock: 'M6 11h12v10H6zM8.5 11V7.5a3.5 3.5 0 0 1 7 0V11',
    scroll: 'M6 3h10a3 3 0 0 1 3 3v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM8 8h7M8 12h7',
    file: 'M6 2h8l6 6v14H6zM14 2v6h6',
    download: 'M12 4v11M7 11l5 5 5-5M4 20h16',
    'arrow-right': 'M4 12h15M13 6l6 6-6 6',
    check: 'M4 12.5l5 5L20 6.5',
    approx: 'M4 9.5c2-2 4-2 6 0s4 2 6 0M4 14.5c2-2 4-2 6 0s4 2 6 0',
    bullet: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
    pin: 'M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zM12 7a2 2 0 1 0 0 4 2 2 0 0 0 0-4z',
  };

  // Dolgu isteyen simgeler (check, sparkle, dot, bullet) stroke ile de okunur;
  // hepsi tek çizim stiliyle tutuldu ki tema rengi (currentColor) eşit uygulansın.
  $: d = PATHS[name] || PATHS.sparkle;
  $: decorative = !label;
</script>

<svg
  class="icon"
  width="{size}em"
  height="{size}em"
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="1.8"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden={decorative ? 'true' : undefined}
  role={decorative ? undefined : 'img'}
  aria-label={decorative ? undefined : label}
  focusable="false"
>
  <path {d} />
</svg>

<style>
  .icon {
    display: inline-block;
    vertical-align: -0.125em;
    flex: 0 0 auto;
    /* Metin akışında satır yüksekliğini bozmasın. */
    line-height: 1;
  }
</style>

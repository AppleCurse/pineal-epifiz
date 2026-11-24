<!--
  Icon.svelte — tek noktadan ikon katmanı.
  Her ikonu currentColor ile çizen satır içi SVG üretir; koyu/açık temada
  otomatik uyum sağlar.
-->
<script lang="ts">
  export let name: string = 'sparkle';
  export let size: number = 1;
  export let label: string = '';

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
    unlock: 'M6 11h12v10H6zM8.5 11V7.5a3.5 3.5 0 0 1 6.7-1.4',
    scroll: 'M6 3h10a3 3 0 0 1 3 3v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM8 8h7M8 12h7',
    file: 'M6 2h8l6 6v14H6zM14 2v6h6',
    download: 'M12 4v11M7 11l5 5 5-5M4 20h16',
    'arrow-right': 'M4 12h15M13 6l6 6-6 6',
    check: 'M4 12.5l5 5L20 6.5',
    approx: 'M4 9.5c2-2 4-2 6 0s4 2 6 0M4 14.5c2-2 4-2 6 0s4 2 6 0',
    bullet: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
    pin: 'M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zM12 7a2 2 0 1 0 0 4 2 2 0 0 0 0-4z',
    sun: 'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
    moon: 'M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z',
    search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-3.8-3.8',
    message: 'M4 5h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 4V7a2 2 0 0 1 2-2z',
    building: 'M4 21h16M6 21V5a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v16M9 8h2M13 8h2M9 12h2M13 12h2M10 21v-4h4v4',
    film: 'M4 4h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM7 4v16M17 4v16M3 12h18',
    mic: 'M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3M8 21h8',
    globe: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM2 12h20M12 2a14 14 0 0 1 0 20M12 2a14 14 0 0 0 0 20',
    folder: 'M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
    sliders: 'M4 6h16M4 12h16M4 18h16M9 4v4M15 10v4M11 16v4',
    shield: 'M12 2l8 4v6c0 5-3.4 9-8 10-4.6-1-8-5-8-10V6z',
    menu: 'M4 6h16M4 12h16M4 18h16',
    copy: 'M9 9h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V10a1 1 0 0 1 1-1zM5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1',
    send: 'M21 3L10 14M21 3l-6 18-4-7-7-4z',
    play: 'M7 5l12 7-12 7z',
    trash: 'M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13',
    scale: 'M12 3v18M5 7h14M5 7l-2 6h4zM19 7l-2 6h4zM8 21h8',
    terminal: 'M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM7 10l3 2.5L7 15M12 15h5',
    users: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM3 20a6 6 0 0 1 12 0M17 11a2.5 2.5 0 1 0 0-5M17 14a4.5 4.5 0 0 1 4 6',
    help: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .8-1 1.7v.5M12 17v.2',
    home: 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z',
    volume: 'M11 5L6 9H3v6h3l5 4zM15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13',
  };

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
    line-height: 1;
  }
</style>

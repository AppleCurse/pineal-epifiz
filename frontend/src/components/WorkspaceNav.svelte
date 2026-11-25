<script lang="ts">
  const items = [
    { id: 'cockpit', label: 'Kokpit' },
    { id: 'strategy', label: 'Aspasia / Lilith' },
    { id: 'browser', label: 'Tarayıcı' },
    { id: 'evidence', label: 'Kanıt' },
    { id: 'jury', label: 'Jüri' },
    { id: 'agents', label: 'Ajanlar' },
    { id: 'cross-scan', label: 'Çapraz Tarama' },
    { id: 'company', label: 'Şirket' },
    { id: 'media', label: 'Medya' },
    { id: 'language', label: 'Dil & Ses' }
  ];
</script>

<nav class="workspace-nav" aria-label="Çalışma alanları">
  <span class="nav-brand">PINEAL <i>／</i> WORKSPACES</span>
  <div class="nav-links">
    {#each items as item}
      <a href="#{item.id}">{item.label}</a>
    {/each}
  </div>
</nav>

<style>
  .workspace-nav {
    position: sticky;
    top: 0;
    z-index: 80;
    display: flex;
    align-items: center;
    gap: 22px;
    width: 100%;
    min-height: 58px;
    padding: 8px clamp(12px, 2.5vw, 34px);
    color: #e8e1d2;
    background: rgba(7, 8, 10, .96);
    border-bottom: 1px solid rgba(190, 157, 93, .28);
    backdrop-filter: blur(18px);
    box-sizing: border-box;
  }
  .nav-brand {
    flex: 0 0 auto;
    color: #d5b779;
    font: 700 10px/1.2 Inter, sans-serif;
    letter-spacing: .18em;
    white-space: nowrap;
  }
  .nav-brand i { color: #7b6846; font-style: normal; }
  .nav-links {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: thin;
    scrollbar-color: #6e5937 transparent;
  }
  .nav-links a {
    flex: 0 0 auto;
    padding: 9px 12px;
    color: #a8a39a;
    border: 1px solid transparent;
    border-radius: 7px;
    text-decoration: none;
    font: 600 11px/1 Inter, sans-serif;
    letter-spacing: .025em;
    transition: color .16s ease, border-color .16s ease, background .16s ease;
  }
  .nav-links a:hover, .nav-links a:focus-visible {
    color: #f2dfb6;
    border-color: rgba(190, 157, 93, .35);
    background: rgba(190, 157, 93, .09);
    outline: none;
  }
  @media (max-width: 720px) {
    .workspace-nav { display: block; padding: 9px 10px 7px; }
    .nav-brand { display: block; margin: 0 0 8px 4px; }
    .nav-links { gap: 3px; }
    .nav-links a { padding: 9px 10px; }
  }
</style>

/**
 * PINEAL-HERETIC v5.0 - Tauri Native Bridge
 * Tarayici sinirlarindan kurtulup dogrudan GPU hizlandirmali native pencere.
 * Bu modul hem Tauri hem de web ortaminda calisir (graceful degrade).
 */

export function isTauri(): boolean {
  if (typeof window === 'undefined') return false;
  // @ts-ignore - Tauri injects __TAURI__ global
  return !!(window as any).__TAURI__ || !!(window as any).__TAURI_INTERNALS__;
}

export async function tauriInvoke<T = any>(cmd: string, args?: Record<string, any>): Promise<T> {
  if (!isTauri()) throw new Error('Tauri ortaminda degil');
  // Dynamic import to avoid bundling issues in web
  const { invoke } = await import('@tauri-apps/api/core');
  return invoke<T>(cmd, args);
}

export async function tauriListen(event: string, handler: (payload: any) => void): Promise<() => void> {
  if (!isTauri()) return () => {};
  const { listen } = await import('@tauri-apps/api/event');
  const unlisten = await listen(event, (ev: any) => {
    handler(ev.payload);
  });
  return unlisten;
}

// Vault islemleri - native
export async function checkVaultStatus(): Promise<boolean> {
  try {
    if (!isTauri()) return false;
    return await tauriInvoke<boolean>('check_vault_status');
  } catch {
    return false;
  }
}

export async function createVault(password: string): Promise<string> {
  return tauriInvoke<string>('create_vault', { password });
}

export async function openVault(password: string): Promise<string> {
  return tauriInvoke<string>('open_vault', { password });
}

export async function lockVault(): Promise<string> {
  return tauriInvoke<string>('lock_vault');
}

export async function vaultExists(): Promise<boolean> {
  try {
    return await tauriInvoke<boolean>('vault_exists');
  } catch {
    return false;
  }
}

export async function setVaultCredentials(key: string, value: string): Promise<string> {
  return tauriInvoke<string>('set_vault_credentials', { key, value });
}

export async function getVaultCredentials(key: string): Promise<string> {
  return tauriInvoke<string>('get_vault_credentials', { key });
}

export async function queryAspasiaNative(userMessage?: string): Promise<string> {
  return tauriInvoke<string>('query_aspasia', { userMessage });
}

export async function startAnalysisNative(
  targetUrl: string,
  scraperType?: string,
  rituals?: string[],
  playlist?: string[],
  envies?: string[]
): Promise<string> {
  return tauriInvoke<string>('start_analysis', {
    targetUrl,
    scraperType,
    userRituals: rituals,
    userPlaylist: playlist,
    userEnvies: envies,
  });
}

export async function emitAgentStatus(agentId: string, status: string, metadata?: any): Promise<string> {
  if (!isTauri()) return 'web-mode';
  return tauriInvoke<string>('emit_agent_status', { agentId, status, metadata });
}

export async function getSystemInfo(): Promise<any> {
  try {
    if (!isTauri()) {
      return {
        product: 'ATLAS PINEAL OBSERVATORY',
        version: '5.0.0',
        build: 'web',
        gpu_acceleration: false,
      };
    }
    return await tauriInvoke<any>('get_system_info');
  } catch {
    return { product: 'ATLAS PINEAL', version: '5.0.0', build: 'unknown' };
  }
}

// GPU hizlandirma kontrolu - CSS will-change ve transform3d zorlamasi
export function enableGPUAcceleration() {
  if (typeof document === 'undefined') return;
  const style = document.createElement('style');
  style.textContent = `
    /* GPU HIZLANDIRMA - Tauri native pencere icin */
    .gpu-accelerated {
      transform: translateZ(0);
      will-change: transform;
      backface-visibility: hidden;
      perspective: 1000px;
    }
    .living-eye-disk, .living-eye-viewport, .holographic-mesh {
      transform: translateZ(0);
      will-change: transform, opacity;
      backface-visibility: hidden;
    }
    /* Canvas optik katman GPU */
    canvas {
      transform: translateZ(0);
      will-change: transform;
    }
  `;
  document.head.appendChild(style);
}

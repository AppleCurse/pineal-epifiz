/**
 * Frontend release identity injected from the repository-root `VERSION` file
 * by `vite.config.ts`. The same value is used in the UI and app signature.
 */
export const APP_VERSION: string = __PINEAL_VERSION__

/** Build signature retained in the bundle and checked by CI. */
export const APP_SIGNATURE = `PINEAL-HERETIC v${APP_VERSION} - ATLAS PINEAL OBSERVATORY`

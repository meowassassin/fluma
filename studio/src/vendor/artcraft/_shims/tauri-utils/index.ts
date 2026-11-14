// FLUMA SHIM for @storyteller/tauri-utils (upstream: frontend/libs/tauri-utils @ 84a6a7d).
// Fluma is a browser app (no Tauri). Only the symbols ArtCraft libs commonly import are
// provided: IsDesktopApp() is always false, FetchProxy is plain window.fetch.
export const IsDesktopApp = (): boolean => false;
export const FetchProxy: typeof fetch = (...args) => fetch(...args);

// FLUMA SHIM (model-list): upstream file copied verbatim from frontend/libs/model-list @ 84a6a7d.
/// Common quality Tauri API
/// Not all models have each of these qualities,
/// but Tauri will interpolate if a mistake is sent.
export enum CommonQuality {
  Auto = "auto",
  Max = "max",
  XHigh = "xhigh",
  High = "high",
  Medium = "medium",
  Low = "low",
}

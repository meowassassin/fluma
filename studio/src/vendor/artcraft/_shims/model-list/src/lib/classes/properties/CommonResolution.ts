// FLUMA SHIM (model-list): upstream file copied verbatim from frontend/libs/model-list @ 84a6a7d.

/// Common aspect ratio Tauri API
/// Not all models have each of these aspect ratios, 
/// but Tauri will interpolate if a mistake is sent.
export enum CommonResolution {
  HalfK = "half_k",
  FourEightyP = "four_eighty_p",
  SevenTwentyP = "seven_twenty_p",
  OneK = "one_k",
  TenEightyP = "ten_eighty_p",
  TwoK = "two_k",
  ThreeK = "three_k",
  FourK = "four_k",
}
// FLUMA SHIM for @storyteller/api (upstream: frontend/libs/api @ 84a6a7d).
// Upstream = HTTP client for the ArtCraft cloud (storyteller.ai) — NOT used in Fluma.
// Types keep the upstream shape; every network call throws a clear error. Libs must
// route uploads/generation through their host adapter (Phase 2+) instead.
import type { UploaderState } from "@storyteller/common";

export const ARTCRAFT_CLOUD_DISABLED = (name: string) => new Error(`ArtCraft cloud not used in Fluma: ${name}`);

export interface ApiResponse<T, P = undefined> {
  success: boolean;
  errorMessage?: string;
  data?: T;
  pagination?: P;
}

export type UploadMediaFn = (args: {
  title: string;
  assetFile: File;
  progressCallback: (newState: UploaderState) => void;
}) => Promise<void>;

export const UploadImageMedia: UploadMediaFn = async () => {
  throw ARTCRAFT_CLOUD_DISABLED("UploadImageMedia");
};

export class ApiManager {
  protected getApiSchemeAndHost(): string {
    throw ARTCRAFT_CLOUD_DISABLED("ApiManager.getApiSchemeAndHost");
  }
}

export class PromptsApi extends ApiManager {
  public async pollJobSession(_jobToken: string, _thumbnailWidth = 256): Promise<ApiResponse<never>> {
    throw ARTCRAFT_CLOUD_DISABLED("PromptsApi.pollJobSession");
  }
  public async uploadSceneSnapshot(_args: { screenshot: File; sceneMediaToken?: string }): Promise<ApiResponse<string>> {
    throw ARTCRAFT_CLOUD_DISABLED("PromptsApi.uploadSceneSnapshot");
  }
}

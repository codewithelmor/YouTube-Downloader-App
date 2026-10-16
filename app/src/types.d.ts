// Ambient types shared by main, preload and renderer (no imports/exports on purpose,
// so the renderer stays a plain browser script).

/** One track as listed by `backend.py --preview`. */
interface TrackPreview {
  video_id: string;
  artist: string;
  title: string;
  album: string | null;
  duration: number;
  cover_url: string | null;
}

/** One subtitle language a video offers (auto = YouTube's auto-generated captions). */
interface SubtitleOption {
  lang: string;
  name: string;
  auto: boolean;
}

interface PreviewData {
  error?: undefined;
  kind: string;
  name: string;
  tracks: TrackPreview[];
  /** Resolutions a single video offers, highest first; empty for playlists. */
  heights: number[];
  /** Subtitle languages a single video offers; empty for playlists (see Api.listSubtitles). */
  subtitles: SubtitleOption[];
}

type PreviewResult = PreviewData | { error: string };

/** Events the Python backend writes as JSON lines (see backend/backend.py). */
type BackendEvent =
  | { event: 'preview'; kind: string; name: string; tracks: TrackPreview[]; heights: number[]; subtitles: SubtitleOption[] }
  | { event: 'subtitles'; subtitles: SubtitleOption[] }
  | { event: 'error'; message: string }
  | { event: 'log'; message: string }
  | { event: 'start'; kind: string; name: string; total: number; folder: string }
  | { event: 'track_start'; index: number; total: number; label: string }
  | { event: 'progress'; percent: number; converting?: boolean }
  | { event: 'track_done'; index: number; label: string }
  | { event: 'track_error'; index: number; label: string; error: string }
  | DoneEvent;

interface DoneEvent {
  event: 'done';
  ok: string[];
  failed: { track: string; error: string }[];
  folder?: string;
  cancelled?: boolean;
  error: string | null;
}

type DownloadMode = 'mp3' | 'video' | 'captions';

interface Settings {
  folder: string;
  bitrate: string;
  enrich: boolean;
  mode: DownloadMode;
  /** Re-encode video to HEVC/x265 (slow). */
  hevc: boolean;
  /** Video resolution cap in pixels of height; '' means best available. */
  maxHeight: string;
  /** Subtitle language codes to save. */
  subLangs: string[];
}

interface DownloadOptions {
  url: string;
  folder: string;
  bitrate: string;
  enrich: boolean;
  mode: DownloadMode;
  hevc: boolean;
  maxHeight: string;
  subLangs: string[];
  trackIds: string[];
}

/** What preload.ts exposes to the renderer as `window.api`. */
interface Api {
  getSettings(): Promise<Settings>;
  saveSettings(settings: Settings): Promise<void>;
  pickFolder(current: string): Promise<string | null>;
  openFolder(folder: string): Promise<string>;
  preview(url: string): Promise<PreviewResult>;
  /** Union of the subtitle languages across a playlist (slow: reads every video). */
  listSubtitles(url: string): Promise<SubtitleOption[] | { error: string }>;
  startDownload(opts: DownloadOptions): Promise<{ started: true } | { error: string }>;
  cancelDownload(): Promise<void>;
  onEvent(handler: (ev: BackendEvent) => void): () => void;
}

interface Window {
  api: Api;
}

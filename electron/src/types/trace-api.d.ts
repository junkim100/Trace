/**
 * Type definitions for the Trace API exposed by preload.js
 */

export interface BackendStatus {
  version: string;
  running: boolean;
  uptime_seconds: number;
  python_version: string;
}

export interface PythonAPI {
  /** Check if Python backend is ready */
  isReady(): Promise<boolean>;

  /** Ping the Python backend */
  ping(): Promise<string>;

  /** Get Python backend status */
  getStatus(): Promise<BackendStatus>;

  /** Generic call to Python backend */
  call<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T>;
}

export interface TraceAPI {
  /** Ping the Electron main process */
  ping(): Promise<string>;

  /** Current platform (darwin, win32, linux) */
  platform: string;

  /** Python backend methods */
  python: PythonAPI;
}

declare global {
  interface Window {
    traceAPI: TraceAPI;
  }
}

// What this does:
//   Streaming configuration overlay with NzbDAV connection settings, stream buffer, and categories

import { Play, X, Activity } from 'lucide-react';
import clsx from 'clsx';
import type { Config } from '../../types';

interface StreamingOverlayProps {
  onClose: () => void;
  config: Config | null;
  setConfig: React.Dispatch<React.SetStateAction<Config | null>>;
  streamingMode: 'nzbdav' | 'stremio';
  setStreamingMode: React.Dispatch<React.SetStateAction<'nzbdav' | 'stremio'>>;
  backend: 'nzbdav' | 'altmount';
  setBackend: React.Dispatch<React.SetStateAction<'nzbdav' | 'altmount'>>;
  altmountUrl: string;
  setAltmountUrl: React.Dispatch<React.SetStateAction<string>>;
  altmountApiKey: string;
  setAltmountApiKey: React.Dispatch<React.SetStateAction<string>>;
  altmountCategory: string;
  setAltmountCategory: React.Dispatch<React.SetStateAction<string>>;
  altmountPrepareTimeout: number;
  setAltmountPrepareTimeout: React.Dispatch<React.SetStateAction<number>>;
  backendMessage: string;
  nzbdavUrl: string;
  setNzbdavUrl: React.Dispatch<React.SetStateAction<string>>;
  nzbdavApiKey: string;
  setNzbdavApiKey: React.Dispatch<React.SetStateAction<string>>;
  nzbdavWebdavUrl: string;
  setNzbdavWebdavUrl: React.Dispatch<React.SetStateAction<string>>;
  nzbdavWebdavUser: string;
  setNzbdavWebdavUser: React.Dispatch<React.SetStateAction<string>>;
  nzbdavWebdavPassword: string;
  setNzbdavWebdavPassword: React.Dispatch<React.SetStateAction<string>>;
  nzbdavMoviesCategory: string;
  setNzbdavMoviesCategory: React.Dispatch<React.SetStateAction<string>>;
  nzbdavTvCategory: string;
  setNzbdavTvCategory: React.Dispatch<React.SetStateAction<string>>;
  nzbdavStreamBufferMB: number;
  setNzbdavStreamBufferMB: React.Dispatch<React.SetStateAction<number>>;
  nzbdavPipeBufferMB: number;
  setNzbdavPipeBufferMB: React.Dispatch<React.SetStateAction<number>>;
  nzbdavStreamingMethod: 'pipe' | 'proxy' | 'direct';
  ultimateFallbackEnabled: boolean;
  nzbdavConnectionStatus: 'connected' | 'disconnected' | 'unconfigured' | 'checking' | null;
  nzbdavTestNzbStatus: 'idle' | 'sending' | 'success' | 'error';
  nzbdavTestNzbMessage: string;
  checkNzbdavConnection: () => Promise<void>;
  sendNzbdavTestNzb: () => Promise<void>;
}

export function StreamingOverlay({
  onClose,
  config,
  setConfig,
  streamingMode,
  setStreamingMode,
  backend,
  setBackend,
  altmountUrl,
  setAltmountUrl,
  altmountApiKey,
  setAltmountApiKey,
  altmountCategory,
  setAltmountCategory,
  altmountPrepareTimeout,
  setAltmountPrepareTimeout,
  backendMessage,
  nzbdavUrl,
  setNzbdavUrl,
  nzbdavApiKey,
  setNzbdavApiKey,
  nzbdavWebdavUrl,
  setNzbdavWebdavUrl,
  nzbdavWebdavUser,
  setNzbdavWebdavUser,
  nzbdavWebdavPassword,
  setNzbdavWebdavPassword,
  nzbdavMoviesCategory,
  setNzbdavMoviesCategory,
  nzbdavTvCategory,
  setNzbdavTvCategory,
  nzbdavStreamBufferMB,
  setNzbdavStreamBufferMB,
  nzbdavPipeBufferMB,
  setNzbdavPipeBufferMB,
  nzbdavStreamingMethod,
  ultimateFallbackEnabled,
  nzbdavConnectionStatus,
  nzbdavTestNzbStatus,
  nzbdavTestNzbMessage,
  checkNzbdavConnection,
  sendNzbdavTestNzb,
}: StreamingOverlayProps) {
  // Backend forces proxy when UF is off — mirror here so the UI stays truthful
  const effectiveMethod = !ultimateFallbackEnabled ? 'proxy' as const : nzbdavStreamingMethod;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={() => onClose()}>
      <div className="bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 rounded-xl border border-slate-700/50 shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto animate-fade-in-up" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 z-10 bg-slate-900/95 backdrop-blur-sm p-4 md:p-6 border-b border-slate-700/50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Play className="w-6 h-6 text-purple-400" />
              <h3 className="text-xl font-semibold text-slate-200">Streaming Configuration</h3>
            </div>
            <button onClick={() => onClose()} className="text-slate-400 hover:text-slate-200 transition-colors">
              <X className="w-6 h-6" />
            </button>
          </div>
        </div>
        <div className="p-4 md:p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">Streaming Mode</label>
            <select
              value={streamingMode}
              onChange={(e) => {
                const newMode = e.target.value as 'nzbdav' | 'stremio';
                setStreamingMode(newMode);
                if (config) setConfig({ ...config, streamingMode: newMode });
              }}
              className="input flex-1 max-w-xs"
            >
              <option value="stremio" disabled>Stremio Native (Unavailable)</option>
              <option value="nzbdav">Backend (NzbDAV or AltMount)</option>
            </select>
            <p className="text-xs text-slate-500 mt-2">
              <strong>Backend:</strong> Stream through a hosted Backend that prepares the chosen Source
            </p>
          </div>

          {streamingMode === 'nzbdav' && (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">Backend</label>
              <select
                value={backend}
                onChange={(e) => setBackend(e.target.value as 'nzbdav' | 'altmount')}
                className="input flex-1 max-w-xs"
              >
                <option value="nzbdav">NzbDAV</option>
                <option value="altmount">AltMount</option>
              </select>
              <p className="text-xs text-slate-500 mt-2">
                Switching Backend keeps the other Backend's settings, so you can switch back at any time.
              </p>
            </div>
          )}

          {streamingMode === 'nzbdav' && (
            <div className="space-y-4">
              {backend === 'altmount' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">AltMount URL</label>
                    <input type="text" value={altmountUrl} onChange={(e) => setAltmountUrl(e.target.value)} placeholder="http://altmount:8080" className="input" />
                    <p className="text-xs text-slate-500 mt-1">AltMount's Stremio integration must be turned on in AltMount's settings.</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-2">AltMount API Key</label>
                    <input type="password" value={altmountApiKey} onChange={(e) => setAltmountApiKey(e.target.value)} placeholder="Your AltMount API key" className="input" />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-2">Category</label>
                      <input type="text" value={altmountCategory} onChange={(e) => setAltmountCategory(e.target.value)} placeholder="kaijuflow" className="input" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-2">Prepare Timeout (seconds)</label>
                      <input type="number" min={1} value={altmountPrepareTimeout} onChange={(e) => setAltmountPrepareTimeout(Math.max(1, parseInt(e.target.value, 10) || 300))} className="input" />
                    </div>
                  </div>
                  <p className="text-xs text-slate-500">Direct delivery hands the player a link that contains AltMount's access key. Keep proxy delivery unless the player is on a trusted network.</p>
                </div>
              )}
              {backend === 'nzbdav' && (<>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">NzbDAV URL</label>
                <input type="text" value={nzbdavUrl} onChange={(e) => setNzbdavUrl(e.target.value)} placeholder="http://localhost:3000" className="input" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">NzbDAV API Key</label>
                <input type="password" value={nzbdavApiKey} onChange={(e) => setNzbdavApiKey(e.target.value)} placeholder="Your NzbDAV API key" className="input" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">WebDAV URL</label>
                <p className="text-xs text-slate-500 mb-1"><span className="text-amber-400/70">Proxy Streaming Method:</span> Use the local/internal hostname for best performance (e.g. http://nzbdav:3000)</p>
                <p className="text-xs text-slate-500 mb-1"><span className="text-amber-400/70">Direct Streaming Method:</span> Must be a publicly reachable URL (e.g. https://nzbdav.example.com) if using a reverse proxy (Traefik, Caddy, Nginx, etc.)</p>
                <p className="text-xs text-slate-500 mb-1"><span className="text-amber-400/70">Direct Streaming Method:</span> If using an auth layer (Authelia, Authentik, etc.), the NzbDAV hostname must bypass auth so Stremio can reach it directly</p>
                <input type="text" value={nzbdavWebdavUrl} onChange={(e) => setNzbdavWebdavUrl(e.target.value)} placeholder="http://localhost:3000" className="input" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">WebDAV Username</label>
                  <input type="text" value={nzbdavWebdavUser} onChange={(e) => setNzbdavWebdavUser(e.target.value)} placeholder="admin" className="input" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">WebDAV Password</label>
                  <input type="password" value={nzbdavWebdavPassword} onChange={(e) => setNzbdavWebdavPassword(e.target.value)} placeholder="password" className="input" />
                </div>
              </div>
              <div className="bg-slate-900/50 rounded-lg border border-slate-700/30 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-slate-300">NZB Mount Categories</div>
                  <button
                    onClick={() => { setNzbdavMoviesCategory('Usenet-Ultimate-Movies'); setNzbdavTvCategory('Usenet-Ultimate-TV'); }}
                    className="text-xs text-primary-400 hover:text-primary-300"
                  >
                    Reset to Defaults
                  </button>
                </div>
                <p className="text-xs text-slate-500">Folder names where NZBs are stored for each content type.</p>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Movies Folder</label>
                    <input type="text" value={nzbdavMoviesCategory} onChange={(e) => setNzbdavMoviesCategory(e.target.value)} placeholder="Usenet-Ultimate-Movies" className="input" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">TV Folder</label>
                    <input type="text" value={nzbdavTvCategory} onChange={(e) => setNzbdavTvCategory(e.target.value)} placeholder="Usenet-Ultimate-TV" className="input" />
                  </div>
                </div>
              </div>
              </>)}
              {/* Stream Buffer Size — hidden in direct mode (no buffer needed); method + range follow effectiveMethod */}
              {effectiveMethod !== 'direct' && (
              <div className="bg-slate-900/50 rounded-lg border border-slate-700/30 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-slate-300">{effectiveMethod === 'pipe' ? 'Pipe Stream Buffer' : 'Dual-Stage Proxy Stream Buffer'}</div>
                  <button
                    onClick={() => effectiveMethod === 'pipe' ? setNzbdavPipeBufferMB(8) : setNzbdavStreamBufferMB(128)}
                    className="text-xs text-primary-400 hover:text-primary-300"
                  >
                    Reset
                  </button>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={effectiveMethod === 'pipe' ? 1 : 8}
                    max={effectiveMethod === 'pipe' ? 16 : 256}
                    step={effectiveMethod === 'pipe' ? 1 : 8}
                    value={effectiveMethod === 'pipe' ? nzbdavPipeBufferMB : nzbdavStreamBufferMB}
                    onChange={(e) => effectiveMethod === 'pipe' ? setNzbdavPipeBufferMB(parseInt(e.target.value, 10)) : setNzbdavStreamBufferMB(parseInt(e.target.value, 10))}
                    className="flex-1 accent-purple-400"
                  />
                  <span className="text-sm text-slate-300 w-16 text-right">{effectiveMethod === 'pipe' ? nzbdavPipeBufferMB : nzbdavStreamBufferMB} MB</span>
                </div>
                <p className="text-xs text-slate-500">
                  {effectiveMethod === 'pipe'
                    ? 'Buffer between WebDAV and the player. Absorbs network jitter with minimal memory usage.'
                    : 'Internal buffer between WebDAV and the player. Larger buffers absorb network jitter but use more memory per stream.'}
                </p>
              </div>
              )}
              <div className={clsx(
                "flex items-center justify-between p-4 rounded-lg border",
                nzbdavConnectionStatus === 'connected' && "bg-green-500/10 border-green-500/30",
                (nzbdavConnectionStatus === 'disconnected' || nzbdavConnectionStatus === 'unconfigured') && "bg-red-500/10 border-red-500/30",
                (nzbdavConnectionStatus === 'checking' || !nzbdavConnectionStatus) && "bg-purple-500/10 border-purple-500/30"
              )}>
                <div className="flex items-center gap-3">
                  <Activity className={clsx(
                    "w-5 h-5",
                    nzbdavConnectionStatus === 'connected' && "text-green-400",
                    (nzbdavConnectionStatus === 'disconnected' || nzbdavConnectionStatus === 'unconfigured') && "text-red-400",
                    (nzbdavConnectionStatus === 'checking' || !nzbdavConnectionStatus) && "text-purple-400"
                  )} />
                  <div>
                    <div className="font-medium text-slate-200">Connection Status</div>
                    <div className={clsx(
                      "text-sm",
                      nzbdavConnectionStatus === 'connected' && "text-green-400",
                      (nzbdavConnectionStatus === 'disconnected' || nzbdavConnectionStatus === 'unconfigured') && "text-red-400",
                      (nzbdavConnectionStatus === 'checking' || !nzbdavConnectionStatus) && "text-slate-400"
                    )}>
                      {nzbdavConnectionStatus === 'checking' && 'Checking connection...'}
                      {nzbdavConnectionStatus === 'connected' && 'Connected'}
                      {nzbdavConnectionStatus === 'disconnected' && 'Disconnected'}
                      {nzbdavConnectionStatus === 'unconfigured' && 'Not configured'}
                      {!nzbdavConnectionStatus && 'Not tested'}
                    </div>
                    {backend === 'altmount' && backendMessage && nzbdavConnectionStatus !== 'checking' && (
                      <div className="text-xs text-slate-400 mt-1">{backendMessage}</div>
                    )}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={checkNzbdavConnection} className="btn text-sm">
                    Test Connection
                  </button>
                  {backend === 'nzbdav' && (<button
                    onClick={sendNzbdavTestNzb}
                    disabled={nzbdavTestNzbStatus === 'sending' || !nzbdavUrl}
                    className="btn text-sm"
                  >
                    {nzbdavTestNzbStatus === 'sending' ? 'Sending...' : 'Send Test NZB'}
                  </button>)}
                </div>
              </div>
              {nzbdavTestNzbMessage && (
                <p className={clsx('text-xs mt-2 px-4 pb-3', nzbdavTestNzbStatus === 'success' ? 'text-green-400' : 'text-red-400')}>
                  {nzbdavTestNzbMessage}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// What this does:
//   Streaming configuration overlay: AltMount (the Backend) connection settings, delivery method and stream buffer

import { Play, X, Activity } from 'lucide-react';
import clsx from 'clsx';

interface StreamingOverlayProps {
  onClose: () => void;
  altmountUrl: string;
  setAltmountUrl: React.Dispatch<React.SetStateAction<string>>;
  altmountApiKey: string;
  setAltmountApiKey: React.Dispatch<React.SetStateAction<string>>;
  altmountCategory: string;
  setAltmountCategory: React.Dispatch<React.SetStateAction<string>>;
  altmountPrepareTimeout: number;
  setAltmountPrepareTimeout: React.Dispatch<React.SetStateAction<number>>;
  backendMessage: string;
  playStreamBufferMB: number;
  setPlayStreamBufferMB: React.Dispatch<React.SetStateAction<number>>;
  playPipeBufferMB: number;
  setPlayPipeBufferMB: React.Dispatch<React.SetStateAction<number>>;
  playDeliveryMethod: 'pipe' | 'proxy' | 'direct';
  setPlayDeliveryMethod: React.Dispatch<React.SetStateAction<'pipe' | 'proxy' | 'direct'>>;
  backendConnectionStatus: 'connected' | 'disconnected' | 'unconfigured' | 'checking' | null;
  checkBackendConnection: () => Promise<void>;
}

export function StreamingOverlay({
  onClose,
  altmountUrl,
  setAltmountUrl,
  altmountApiKey,
  setAltmountApiKey,
  altmountCategory,
  setAltmountCategory,
  altmountPrepareTimeout,
  setAltmountPrepareTimeout,
  backendMessage,
  playStreamBufferMB,
  setPlayStreamBufferMB,
  playPipeBufferMB,
  setPlayPipeBufferMB,
  playDeliveryMethod,
  setPlayDeliveryMethod,
  backendConnectionStatus,
  checkBackendConnection,
}: StreamingOverlayProps) {
  const effectiveMethod = playDeliveryMethod;
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
          <div className="space-y-4">
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
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Delivery Method</label>
                  <div className="flex gap-2" role="radiogroup">
                    {(['proxy', 'pipe', 'direct'] as const).map((method) => (
                      <button
                        key={method}
                        type="button"
                        role="radio"
                        aria-checked={playDeliveryMethod === method}
                        onClick={() => setPlayDeliveryMethod(method)}
                        className={clsx(
                          "flex-1 px-4 py-2 rounded-lg text-sm font-medium border transition-colors",
                          playDeliveryMethod === method
                            ? "bg-purple-500/20 border-purple-500/50 text-purple-300"
                            : "bg-slate-700/50 border-slate-600 text-slate-400 hover:text-slate-300"
                        )}
                      >
                        {method === 'pipe' ? 'Pipe' : method === 'proxy' ? 'Dual-Stage Proxy' : 'Direct'}
                      </button>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-slate-500">Direct delivery hands the player a link that contains AltMount's access key. Keep proxy delivery unless the player is on a trusted network.</p>
              </div>
            {/* Stream Buffer Size — hidden in direct mode (no buffer needed); method + range follow effectiveMethod */}
            {effectiveMethod !== 'direct' && (
            <div className="bg-slate-900/50 rounded-lg border border-slate-700/30 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium text-slate-300">{effectiveMethod === 'pipe' ? 'Pipe Stream Buffer' : 'Dual-Stage Proxy Stream Buffer'}</div>
                <button
                  onClick={() => effectiveMethod === 'pipe' ? setPlayPipeBufferMB(8) : setPlayStreamBufferMB(128)}
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
                  value={effectiveMethod === 'pipe' ? playPipeBufferMB : playStreamBufferMB}
                  onChange={(e) => effectiveMethod === 'pipe' ? setPlayPipeBufferMB(parseInt(e.target.value, 10)) : setPlayStreamBufferMB(parseInt(e.target.value, 10))}
                  className="flex-1 accent-purple-400"
                />
                <span className="text-sm text-slate-300 w-16 text-right">{effectiveMethod === 'pipe' ? playPipeBufferMB : playStreamBufferMB} MB</span>
              </div>
              <p className="text-xs text-slate-500">
                {effectiveMethod === 'pipe'
                  ? 'Buffer between AltMount and the player. Absorbs network jitter with minimal memory usage.'
                  : 'Internal buffer between AltMount and the player. Larger buffers absorb network jitter but use more memory per stream.'}
              </p>
            </div>
            )}
            <div className={clsx(
              "flex items-center justify-between p-4 rounded-lg border",
              backendConnectionStatus === 'connected' && "bg-green-500/10 border-green-500/30",
              (backendConnectionStatus === 'disconnected' || backendConnectionStatus === 'unconfigured') && "bg-red-500/10 border-red-500/30",
              (backendConnectionStatus === 'checking' || !backendConnectionStatus) && "bg-purple-500/10 border-purple-500/30"
            )}>
              <div className="flex items-center gap-3">
                <Activity className={clsx(
                  "w-5 h-5",
                  backendConnectionStatus === 'connected' && "text-green-400",
                  (backendConnectionStatus === 'disconnected' || backendConnectionStatus === 'unconfigured') && "text-red-400",
                  (backendConnectionStatus === 'checking' || !backendConnectionStatus) && "text-purple-400"
                )} />
                <div>
                  <div className="font-medium text-slate-200">Connection Status</div>
                  <div className={clsx(
                    "text-sm",
                    backendConnectionStatus === 'connected' && "text-green-400",
                    (backendConnectionStatus === 'disconnected' || backendConnectionStatus === 'unconfigured') && "text-red-400",
                    (backendConnectionStatus === 'checking' || !backendConnectionStatus) && "text-slate-400"
                  )}>
                    {backendConnectionStatus === 'checking' && 'Checking connection...'}
                    {backendConnectionStatus === 'connected' && 'Connected'}
                    {backendConnectionStatus === 'disconnected' && 'Disconnected'}
                    {backendConnectionStatus === 'unconfigured' && 'Not configured'}
                    {!backendConnectionStatus && 'Not tested'}
                  </div>
                  {backendMessage && backendConnectionStatus !== 'checking' && (
                    <div className="text-xs text-slate-400 mt-1">{backendMessage}</div>
                  )}
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={checkBackendConnection} className="btn text-sm">
                  Test Connection
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

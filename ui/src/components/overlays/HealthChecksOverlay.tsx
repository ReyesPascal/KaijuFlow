// What this does:
//   Health checks overlay for configuring the NNTP health check providers, the connection cap
//   and TLS, and whether EasyNews results carry a verified mark on the list. A Source is checked
//   when it is played (Play-time check); the list-time Smart and Fixed settings were deleted in
//   #191 and Auto-queue in #226.

import { Heart, X } from 'lucide-react';
import type { Config, HealthChecksState, UsenetProvider } from '../../types';
import { ProviderManager } from '../shared/ProviderManager';
import { DEFAULT_HEALTH_CHECKS } from '../../constants';
interface HealthChecksOverlayProps {
  onClose: () => void;
  config: Config | null;
  healthChecks: HealthChecksState;
  setHealthChecks: React.Dispatch<React.SetStateAction<HealthChecksState>>;
  apiFetch: (url: string, options?: RequestInit) => Promise<Response>;
  easynewsHealthCheck: boolean;
  setEasynewsHealthCheck: React.Dispatch<React.SetStateAction<boolean>>;
}

export default function HealthChecksOverlay({
  onClose,
  config,
  healthChecks,
  setHealthChecks,
  apiFetch,
  easynewsHealthCheck,
  setEasynewsHealthCheck,
}: HealthChecksOverlayProps) {
  // Provider change handler for the shared ProviderManager component
  const handleProvidersChange = (providers: UsenetProvider[]) => {
    setHealthChecks(prev => ({ ...prev, providers }));
  };

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={() => onClose()}>
        <div className="bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 rounded-xl border border-slate-700/50 shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto animate-fade-in-up" onClick={(e) => e.stopPropagation()}>
          <div className="sticky top-0 z-10 bg-slate-900/95 backdrop-blur-sm p-4 md:p-6 border-b border-slate-700/50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Heart className="w-6 h-6 text-pink-400" />
                <h3 className="text-xl font-semibold text-slate-200">Health Checks</h3>
              </div>
              <button onClick={() => onClose()} className="text-slate-400 hover:text-slate-200 transition-colors">
                <X className="w-6 h-6" />
              </button>
            </div>
          </div>

          <div className="p-4 md:p-6 space-y-6">
            <p className="text-sm text-slate-400">
              Each Source is checked when it is played, never before the stream list is shown: KaijuFlow hands AltMount only a Source whose articles are there and whose archive it can stream.
            </p>

            <div className="space-y-6">
            {/* Health Check Options */}
            <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700 space-y-4">
              <h4 className="text-sm font-semibold text-slate-300">Health Check Options</h4>

              {/* Sub-options */}
              <div className="space-y-3">
                {config?.easynewsEnabled && config?.easynewsMode === 'nzb' && (
                  <div>
                    <label className="flex items-center gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={easynewsHealthCheck}
                        onChange={(e) => setEasynewsHealthCheck(e.target.checked)}
                        className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-pink-500 focus:ring-pink-500 focus:ring-offset-slate-800"
                      />
                      <span className="text-sm font-medium text-slate-300">No ✅ Mark on EasyNews Results</span>
                    </label>
                    <p className="text-xs text-slate-500 mt-1 ml-7">
                      On: EasyNews results show no mark on the stream list, like every other Source.
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5 ml-7">
                      Off: they show ✅, as EasyNews found them. Either way each one is checked when it is played.
                    </p>
                  </div>
                )}
                <div>
                  <label className="flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={healthChecks.verifyTlsCertificates ?? DEFAULT_HEALTH_CHECKS.verifyTlsCertificates}
                      onChange={(e) => setHealthChecks({ ...healthChecks, verifyTlsCertificates: e.target.checked })}
                      className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-pink-500 focus:ring-pink-500 focus:ring-offset-slate-800"
                    />
                    <span className="text-sm font-medium text-slate-300">Verify TLS Certificates</span>
                  </label>
                  <p className="text-xs text-slate-500 mt-1 ml-7">
                    Reject Usenet servers whose TLS certificate is invalid, expired, self-signed or for a different hostname (default on). Applies to health checks and Test Connection.
                    {' '}<span className="text-amber-400/80">Turning this off lets anyone between you and the server (on your network or ISP) pose as your provider and read your Usenet username and password. Only turn it off for a server you trust, such as one with a self-signed certificate on your own network.</span>
                  </p>
                </div>
              </div>
            </div>

            {/* Stream Status Legend */}
            <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700">
              <h4 className="text-sm font-semibold text-slate-300 mb-3">Stream List Marks</h4>
              <div className="space-y-3 text-sm">
                <div className="flex items-start gap-3">
                  <span className="text-lg leading-none mt-0.5">✅</span>
                  <div>
                    <div className="font-medium text-green-400">EasyNews</div>
                    <div className="text-slate-400 text-xs">Found on EasyNews (unless the option above is on). Still checked when it is played.</div>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-lg leading-none mt-0.5">🤖</span>
                  <div>
                    <div className="font-medium text-green-400">Zyclops</div>
                    <div className="text-slate-400 text-xs">Verified by Zyclops. Still checked when it is played.</div>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-lg leading-none mt-0.5 w-5 text-center text-slate-500">·</span>
                  <div>
                    <div className="font-medium text-slate-300">No mark</div>
                    <div className="text-slate-400 text-xs">Not checked yet: every Source is checked when it is played. One the check blocks (missing articles, an archive AltMount cannot stream, a disc image) is never handed to AltMount, the next Source plays instead, and it leaves the list.</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Usenet Providers (shared component) */}
            <ProviderManager
              providers={healthChecks.providers}
              onProvidersChange={handleProvidersChange}
              apiFetch={apiFetch}
              accentColor="pink"
            />

            {/* Health Check Settings */}
            <div className="space-y-4">
              <h4 className="text-sm font-semibold text-slate-300">Settings</h4>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Max Total Connections</label>
                <input
                  type="number"
                  value={healthChecks.maxTotalConnections ?? ''}
                  onChange={(e) => setHealthChecks({ ...healthChecks, maxTotalConnections: e.target.value === '' ? ('' as any) : parseInt(e.target.value) || 1 })}
                  onFocus={(e) => e.target.select()}
                  onBlur={(e) => { if (e.target.value === '' || parseInt(e.target.value) < 1) setHealthChecks(prev => ({ ...prev, maxTotalConnections: DEFAULT_HEALTH_CHECKS.maxTotalConnections })); }}
                  min="1"
                  max="100"
                  className="input w-full"
                />
                <p className="text-xs text-slate-500 mt-1">
                  Health checks never hold more Usenet connections than this, across all checks and providers combined (default {DEFAULT_HEALTH_CHECKS.maxTotalConnections}, max 100). Extra checks wait their turn; results are the same, only slower.
                  {' '}<span className="text-amber-400/80">This number plus AltMount's connections must not exceed your provider's maximum allowed connections.</span>
                </p>
              </div>
            </div>

            {/* Reset Button */}
            <div className="pt-4 border-t border-slate-700">
              <button
                onClick={() => {
                  setHealthChecks(prev => ({
                    providers: prev.providers,
                    maxTotalConnections: DEFAULT_HEALTH_CHECKS.maxTotalConnections,
                    verifyTlsCertificates: DEFAULT_HEALTH_CHECKS.verifyTlsCertificates,
                  }));
                }}
                className="btn-secondary w-full"
              >
                Reset to Default
              </button>
            </div>
            </div>
          </div>
        </div>
      </div>

    </>
  );
}

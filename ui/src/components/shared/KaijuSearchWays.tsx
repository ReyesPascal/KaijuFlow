import type { IndexerCaps } from '../../types';

// Kaiju Search (#285): every indexer is asked by name and by every ID its capabilities list, so there is no search
// method to choose. This shows what an indexer is asked by (the server's rule is `idWaysOf` in src/addon/kaijuSearch.ts).
const ID_LABELS: Record<'movie' | 'tv', [string, string][]> = {
  movie: [['imdbid', 'IMDb'], ['tmdbid', 'TMDB'], ['tvdbid', 'TVDB']],
  tv: [['imdbid', 'IMDb'], ['tvdbid', 'TVDB'], ['tvmazeid', 'TVmaze']],
};

function idsOf(caps: IndexerCaps | null | undefined, kind: 'movie' | 'tv'): string[] {
  const params = (kind === 'movie' ? caps?.movieSearchParams : caps?.tvSearchParams)?.map(p => p.toLowerCase());
  if (!params || (params.length === 0 && caps?.version === undefined)) return ['IMDb']; // unknown (a legacy [] too); [] read as not available asks by no ID
  return ID_LABELS[kind].filter(([p]) => params.includes(p)).map(([, label]) => label);
}

export function KaijuSearchWays({ caps }: { caps: IndexerCaps | null | undefined }) {
  const ways = (kind: 'movie' | 'tv') => ['name', ...idsOf(caps, kind)].join(', ');
  return (
    <div className="text-xs text-slate-400 space-y-1">
      <p>
        <span className="bg-gradient-to-r from-amber-300 via-yellow-400 to-amber-400 bg-clip-text text-transparent font-semibold">Kaiju Search</span>{' '}
        asks this indexer by name and by every ID it supports, at once.
      </p>
      <p>Movies: {ways('movie')} · TV: {ways('tv')}</p>
      {!caps && <p className="text-slate-500">Capabilities unknown: asked by IMDb. Discover them to ask by every ID it supports.</p>}
    </div>
  );
}

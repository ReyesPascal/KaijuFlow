/**
 * Newznab XML parsing and indexer capabilities discovery.
 *
 * Provides shared parsers for Newznab RSS XML responses, including
 * pagination metadata extraction and the ?t=caps endpoint.
 */

import axios from 'axios';
import { parseStringPromise } from 'xml2js';
import { NZBSearchResult, IndexerCaps } from '../types.js';
import { config } from '../config/index.js';
import { getLatestVersions } from '../versionFetcher.js';
import { getAxiosProxyConfig } from '../proxy.js';
import { CAPS_VERSION } from '../config/capsMigration.js';

// Parsed response with pagination metadata
export interface NewznabParsedResponse {
  results: NZBSearchResult[];
  total?: number;    // from <newznab:response total="...">
  offset?: number;   // from <newznab:response offset="...">
}

// Shared Newznab XML parser with pagination metadata
// Extracts NZBSearchResult[] plus total/offset from <newznab:response>
export async function parseNewznabXmlWithMeta(xmlData: string): Promise<NewznabParsedResponse> {
  const parsed = await parseStringPromise(xmlData);

  // Extract pagination from <newznab:response offset="0" total="500" />
  let total: number | undefined;
  let offset: number | undefined;
  const newznabResponse = parsed.rss?.channel?.[0]?.['newznab:response']?.[0];
  if (newznabResponse?.$) {
    total = parseInt(newznabResponse.$.total, 10) || undefined;
    offset = parseInt(newznabResponse.$.offset, 10) || undefined;
  }

  if (!parsed.rss?.channel?.[0]?.item) {
    return { results: [], total, offset };
  }

  const items = parsed.rss.channel[0].item;

  const results = items.map((item: any) => {
    const attrs: any = {};

    // Collect attributes from all possible namespaced element sources.
    // NZBHydra2 may use different element names depending on version/config.
    const attrSources = [
      item['newznab:attr'],
      item['newznab:attrs'],
      item['nzbhydra:attr'],
      item['nzbhydra:attrs'],
      item.attr,
      item.attrs,
    ];
    for (const source of attrSources) {
      if (!Array.isArray(source)) continue;
      for (const attr of source) {
        if (attr?.$?.name && attr.$.value !== undefined) {
          const key = attr.$.name.toLowerCase();
          if (attrs[key] === undefined) attrs[key] = attr.$.value;
        }
      }
    }

    // Size: prefer newznab:attr, fall back to <enclosure length="...">
    const enclosureLength = item.enclosure?.[0]?.$?.length;
    const size = parseInt(attrs.size || enclosureLength || '0', 10);

    return {
      title: (() => { const raw = item.title?.[0] || ''; if (!raw.includes('%')) return raw; try { return decodeURIComponent(raw); } catch { return raw; } })(),
      link: item.link?.[0] || item.guid?.[0]?._ || item.guid?.[0] || '',
      size,
      pubDate: item.pubDate?.[0] || '',
      category: attrs.category || '',
      attributes: attrs,
    };
  });

  return { results, total, offset };
}

// Backward-compatible wrapper — extracts NZBSearchResult[] only
// Used by NzbhydraSearcher and other consumers that don't need pagination
export async function parseNewznabXml(xmlData: string): Promise<NZBSearchResult[]> {
  const { results } = await parseNewznabXmlWithMeta(xmlData);
  return results;
}

/** One kind of search on a caps reply's <searching> line: its params; [] when it says available="no"; undefined when
 *  it cannot be read (no such line, or no supportedParams): unknown, so Kaiju Search asks by IMDb (idWaysOf). */
function searchParams(line: any): string[] | undefined {
  const at = line?.$;
  if (!at) return undefined;
  if (at.available === 'no') return [];
  if ((at.available !== undefined && at.available !== 'yes') || typeof at.supportedParams !== 'string') return undefined;
  return at.supportedParams.split(',').map((p: string) => p.trim().toLowerCase()).filter(Boolean);
}

/** The caps a parsed (xml2js) Newznab caps reply holds, or undefined when it has no <searching> block: a Newznab
 *  <error> (a wrong key, a reached limit) is sent with HTTP 200 and holds none. The Newznab fetch and NZBHydra's sync
 *  read caps through this. */
export function capsOfReply(parsed: any): IndexerCaps | undefined {
  const searching = parsed?.caps?.searching?.[0];
  if (!searching || typeof searching !== 'object') return undefined;
  return { version: CAPS_VERSION, movieSearchParams: searchParams(searching['movie-search']?.[0]),
    tvSearchParams: searchParams(searching['tv-search']?.[0]) };
}

/**
 * Fetch indexer capabilities via the Newznab ?t=caps endpoint.
 * Parses the <searching> block to discover supported params for movie-search and tv-search.
 */
export async function fetchIndexerCaps(
  url: string,
  apiKey: string,
  indexerName?: string,
  zyclops?: import('../types.js').ZyclopsIndexerConfig
): Promise<IndexerCaps> {
  const userAgent = config.userAgents?.indexerSearch || getLatestVersions().chrome;

  // Determine effective URL: use Zyclops proxy if enabled
  let effectiveUrl = url;
  let extraParams: Record<string, string> = {};
  const isZyclops = zyclops?.enabled === true;

  if (isZyclops) {
    const zyclopsEndpoint = config.zyclopsEndpoint || 'https://zyclops.elfhosted.com';
    effectiveUrl = `${zyclopsEndpoint.replace(/\/$/, '')}/api`;
    extraParams = { target: url };
    if (zyclops.backbone?.length) extraParams.backbone = zyclops.backbone.join(',');
    if (zyclops.providerHosts) extraParams.provider_host = zyclops.providerHosts;
    console.log(`🤖 Fetching caps via Zyclops for ${indexerName || 'unknown'}: ${url} → ${effectiveUrl}`);
  }

  const response = await axios.get(effectiveUrl, {
    params: { t: 'caps', apikey: apiKey, ...extraParams },
    timeout: isZyclops ? 30000 : 10000,
    headers: { 'User-Agent': userAgent },
    ...(isZyclops ? {} : getAxiosProxyConfig(url, indexerName)),
  });

  const parsed = await parseStringPromise(response.data);
  const caps = capsOfReply(parsed);
  if (!caps) {
    const e = parsed?.error?.$;
    throw new Error(e ? `the indexer answered error ${e.code}: ${e.description}` : 'no <searching> block in the caps reply');
  }

  const shown = (ps?: string[]) => (ps ? `[${ps.join(', ')}]` : 'unknown');
  console.log(`🔍 Caps discovered: movie=${shown(caps.movieSearchParams)}, tv=${shown(caps.tvSearchParams)}`);
  return caps;
}

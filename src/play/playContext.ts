/**
 * The play context (GLOSSARY: Play context, #246): what a play of a list is for (type, season, episode, aired date,
 * episodes in season, Best's session). Made once when the list is built and stored on its fallback group; the Head
 * start, a press of Best and a list-entry play all read it, so each looks for the same episode. It holds identity
 * only: how a Source is keyed for the play is the Source memory's (`sourceMemory.ts`, #247).
 */

import { config as globalConfig, getTvAllowMultiEpisode } from '../config/index.js';
import { buildEpisodePattern, buildDateEpisodePattern } from './utils.js';

export interface PlayContext {
  /** Best's session for this title: one per installation (manifest key), title and episode. Empty without an id. */
  sessionKey: string;
  type: string;
  season?: number;
  episode?: number;
  /** Aired date (YYYY-MM-DD), for a daily show whose files are named by date. */
  aired?: string;
  episodesInSeason?: number;
}

/**
 * Best's session key. It includes the manifest key so two Stremio installations asking for the same title don't
 * share Best's session state.
 */
export function sessionKeyOf(manifestKey: string, type: string, imdbId: string | undefined, season?: number, episode?: number): string {
  return imdbId ? `${manifestKey}:${type}:${imdbId}:${season ?? ''}:${episode ?? ''}` : '';
}

export function makePlayContext(title: {
  manifestKey: string;
  type: string;
  imdbId?: string;
  season?: number;
  episode?: number;
  aired?: string;
  episodesInSeason?: number;
}): PlayContext {
  const { manifestKey, type, imdbId, season, episode, aired, episodesInSeason } = title;
  return {
    sessionKey: sessionKeyOf(manifestKey, type, imdbId, season, episode),
    type,
    ...(season !== undefined ? { season } : {}),
    ...(episode !== undefined ? { episode } : {}),
    ...(aired ? { aired } : {}),
    ...(episodesInSeason !== undefined ? { episodesInSeason } : {}),
  };
}

/** What a season pack's tile envelope carries of its play context, so a play of it finds the episode once the
 *  fallback group is gone (expired, or not kept over a restart). Nothing without a season and an episode. */
export function episodeForTile(play: PlayContext): { season?: number; episode?: number; seasonpack?: 1; epcount?: number; aired?: string } {
  if (play.season === undefined || play.episode === undefined) return {};
  return {
    season: play.season, episode: play.episode, seasonpack: 1,
    ...(play.episodesInSeason ? { epcount: play.episodesInSeason } : {}),
    ...(play.aired ? { aired: play.aired } : {}),
  };
}

/** A list entry's play context read back from its tile envelope (episodeForTile), when its fallback group is gone. */
export function playContextOfTile(tile: { sk?: string; ty?: string; season?: number; episode?: number; epcount?: number; aired?: string }): PlayContext {
  return {
    sessionKey: tile.sk ?? '',
    type: tile.ty ?? '',
    ...(tile.season !== undefined ? { season: tile.season } : {}),
    ...(tile.episode !== undefined ? { episode: tile.episode } : {}),
    ...(tile.aired ? { aired: tile.aired } : {}),
    ...(tile.epcount !== undefined ? { episodesInSeason: tile.epcount } : {}),
  };
}

/**
 * The episode a play is for, as the patterns that find it: `episodePattern` (SxxExx) and `filePattern`, which also
 * finds a file named by the episode's aired date. Neither without a season and an episode.
 */
export function episodeOf(play: PlayContext | undefined): { episodePattern?: string; filePattern?: string } {
  if (play?.season === undefined || play.episode === undefined) return {};
  const episodePattern = buildEpisodePattern(play.season, play.episode, getTvAllowMultiEpisode(globalConfig));
  const datePattern = buildDateEpisodePattern(play.aired);
  return { episodePattern, filePattern: datePattern ? `(?:${episodePattern}|${datePattern})` : episodePattern };
}

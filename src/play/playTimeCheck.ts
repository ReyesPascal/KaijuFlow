/**
 * Play-time check (GLOSSARY, spec #183, #190).
 *
 * The health check runs when a Source is about to be played, not before the
 * stream list is sent: the list goes out at once, unchecked, with the Best
 * entry on top. Ultimate Fallback's engine is its engine (the Best entry);
 * a list entry is checked when it is clicked. KaijuFlow never hands the
 * Backend an Unchecked Source.
 */

import { isUltimateFallbackActive } from './utils.js';

/** True when the Play-time check is on: Ultimate Fallback is on and the Backend can run it (AltMount since #190). */
export function isPlayTimeCheckOn(): boolean {
  return isUltimateFallbackActive();
}

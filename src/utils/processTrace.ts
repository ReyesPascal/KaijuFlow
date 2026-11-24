/**
 * Process trace (#249): what the whole Node process did while one piece of work ran, for its step line.
 *
 * A warm list's own work got slower in #219 by the same factor in every step, which points at the process (CPU,
 * garbage collection, a busy event loop), not at the list's code. A trace measures that process around the work:
 * CPU time, garbage-collection pauses, event-loop delay and use, heap. Everything here is the whole process, so other
 * work running at the same time (a Head start, a play) shows in it; that is the point.
 */
import { monitorEventLoopDelay, performance, PerformanceObserver, type PerformanceEntry } from 'node:perf_hooks';

/** The trace's fields as a step line carries them (whole milliseconds, ELU 0–1 to two places, heap in MB). */
export interface ProcessTraceFields {
  /** Process CPU time (user + system) while the work ran. */
  cpu_ms: number;
  /** Garbage-collection pauses while the work ran: their total and how many. */
  gc_ms: number;
  gc_n: number;
  /** Event-loop delay while the work ran: the longest and the 99th percentile (sampled every 2 ms). */
  loop_max_ms: number;
  loop_p99_ms: number;
  /** Event-loop utilization while the work ran: the share of the time the loop was busy. */
  elu: number;
  /** Heap in use when the work ended. */
  heap_mb: number;
}

// Garbage-collection pauses, added up for the whole process since the first trace began.
let gcTotalMs = 0;
let gcCount = 0;
let gcObserver: PerformanceObserver | undefined;

function add(entries: PerformanceEntry[]): void {
  for (const e of entries) { gcTotalMs += e.duration; gcCount++; }
}

function observeGc(): void {
  if (gcObserver) return;
  gcObserver = new PerformanceObserver(list => add(list.getEntries()));
  gcObserver.observe({ entryTypes: ['gc'] });
}

/** Start a trace; the returned function ends it and gives its fields. */
export function startProcessTrace(): () => ProcessTraceFields {
  observeGc();
  const cpu0 = process.cpuUsage();
  const elu0 = performance.eventLoopUtilization();
  const gc0 = { ms: gcTotalMs, n: gcCount };
  const delay = monitorEventLoopDelay({ resolution: 2 });
  delay.enable();
  return () => {
    // A collection's entry is queued a turn of the loop after it ends, and reaches the callback later still: end a
    // trace one turn after its work (setImmediate) to count the work's last collection, and take what still waits.
    add(gcObserver?.takeRecords() ?? []);
    delay.disable();
    const cpu = process.cpuUsage(cpu0);
    const elu = performance.eventLoopUtilization(elu0);
    // The histogram counts in nanoseconds and holds its resolution in every sample: take it off.
    const ms = (ns: number) => Math.max(0, Math.round(ns / 1e6 - 2));
    return {
      cpu_ms: Math.round((cpu.user + cpu.system) / 1000),
      gc_ms: Math.round(gcTotalMs - gc0.ms),
      gc_n: gcCount - gc0.n,
      loop_max_ms: delay.count ? ms(delay.max) : 0,
      loop_p99_ms: delay.count ? ms(delay.percentile(99)) : 0,
      elu: Math.round(elu.utilization * 100) / 100,
      heap_mb: Math.round(process.memoryUsage().heapUsed / 1048576),
    };
  };
}

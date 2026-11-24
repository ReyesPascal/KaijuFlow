Captured on Brain on 2026-11-24, plugged in, for the preflight's power check and the run record's `machine` (#262, `test_preflight.py` `PowerReadersTest`, `PowerWiringTest`):

- `power_supply/`: `/sys/class/power_supply/`, each supply's `type`, `online` and `status` (where the supply has them), copied as they were: the AC adapter (`AC`, type `Mains`, online), the battery (`BAT0`, type `Battery`, charging, no `online`) and two USB-C ports (type `USB`, one online). The tests make the on-battery tree from this one by writing `0` into `AC/online`, and a desktop's by leaving the `Mains` supply out.
- `cpufreq/`: `/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor` (`powersave`) and `energy_performance_preference` (`performance`).

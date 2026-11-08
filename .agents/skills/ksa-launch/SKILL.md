---
name: ksa-launch
description: Launch Kitten Space Agency through StarMap for local mod testing, including isolated-instance launches and the profiler CSV capture harness. Use when asked to start or run the game, test a mod in game, or capture profiler output.
---

# Launching KSA

KSA is always started through the StarMap launcher — never `KSA.exe` directly. Mods only
load via StarMap.

Confirm with the user before actually starting the game; a launch is a real side effect.
Have the exact command ready, including any environment variables.

## Locate StarMap

StarMap lives in the KSA user mods folder:

`%USERPROFILE%\Documents\My Games\Kitten Space Agency\mods\StarMap\StarMap.exe`

- Launch `StarMap.exe` with its own directory as the working directory — it reads
  `StarMapConfig.json` relative to the exe's folder, not the caller's.
- `StarMapConfig.json` holds `GameLocation` (the KSA install dir, e.g.
  `C:\Program Files\Kitten Space Agency`), `RepositoryLocation` (leave empty), and
  `GameArguments` (extra CLI arguments forwarded to the game).
- Requires the .NET 10 runtime.

## Normal launch (default profile)

Set per-run environment variables in the same shell that starts StarMap, then launch it.
Environment variables are inherited by the game process and apply to that launch only —
they do not persist.

PowerShell:

```powershell
$starMap = "$env:USERPROFILE\Documents\My Games\Kitten Space Agency\mods\StarMap"
$env:KSA_PROFILE_CAPTURE      = 'MySave'
$env:KSA_PROFILE_CAPTURE_GPU  = '1'
$env:KSA_PROFILE_CAPTURE_OUT  = 'C:\caps\run1.csv'
Start-Process -FilePath "$starMap\StarMap.exe" -WorkingDirectory $starMap
```

cmd:

```bat
cd /d "%USERPROFILE%\Documents\My Games\Kitten Space Agency\mods\StarMap"
set KSA_PROFILE_CAPTURE=MySave
set KSA_PROFILE_CAPTURE_GPU=1
set KSA_PROFILE_CAPTURE_OUT=C:\caps\run1.csv
StarMap.exe
```

The built mod must already be deployed to the mods folder — `KsaMod.targets` copies build
output to `$(KSAModsDir)<ModName>/` (`Documents\My Games\Kitten Space Agency\mods\` by
default) unless `CopyToLocalMods=false` or `CI=true`.

## Isolated instance (only when required)

To test a mod isolated from the normal profile and mod set, point StarMap at a different
instance directory. This replaces the entire KSA user-data directory — `mods/`,
`manifest.toml`, saves and logs — not just the mods folder:

- `STARMAP_INSTANCE_PATH=<instance dir>` as a process-scoped environment variable
  (preferred for one-off runs), or
- `-InstancePath <dir>` as a game argument via `GameArguments` in `StarMapConfig.json`.

The instance directory must contain:

- `manifest.toml` at its root with `[[mods]]` entries (`id`, `enabled`) — `Core` plus the
  mod under test:

  ```toml
  [[mods]]
  id = "Core"
  enabled = true

  [[mods]]
  id = "MyMod"
  enabled = true
  ```

- `mods/<ModId>/` holding the mod files, including a `mod.toml` with
  `[StarMap] EntryAssembly = "<assembly name>"`.

Use an isolated instance only when the task actually requires isolation — for example
controlled A/B profiler captures or reproducing a bug without other mods loaded.
Otherwise launch the normal profile.

## Profiler export harness

Set these environment variables in the shell that launches the game; they apply to that
launch only:

- `KSA_PROFILE_CAPTURE=<save name>` — loads the named save, runs the profiler, and dumps
  the results to CSV.
- `KSA_PROFILE_CAPTURE_GPU=1` — include GPU timings in the capture.
- `KSA_PROFILE_CAPTURE_OUT=<path>` — output CSV path; create the directory beforehand.

The named save must exist in the active instance — the default profile, or the
`-InstancePath` instance when running isolated. For reliable A/B comparisons keep the
workload identical between runs and vary only the thing under test; each run needs its own
fresh `KSA_PROFILE_CAPTURE_OUT` path so results are never overwritten.

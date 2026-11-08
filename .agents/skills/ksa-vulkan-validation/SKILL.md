---
name: ksa-vulkan-validation
description: Run KSA with the Khronos Vulkan validation layer enabled to catch Vulkan API misuse by the game or a mod. Use when asked to validate Vulkan usage, investigate rendering crashes/undefined behavior, or do validation-enabled A/B runs. Requires the ksa-launch skill for game launch mechanics.
---

# Vulkan validation for KSA mods

Runs an isolated KSA instance with `VK_LAYER_KHRONOS_validation` enabled so Vulkan API
errors made by the game or an injected mod are reported instead of silently producing
undefined behavior.

Use the `ksa-launch` skill for StarMap location, config, and launch mechanics — this
skill layers validation environment variables on top of a normal launch and **requires an
isolated instance** (`STARMAP_INSTANCE_PATH`), which `ksa-launch` documents.

## What this is (and is not)

The layer checks supported Vulkan API usage against the specification (state,
synchronization, object lifetimes, handles, parameters). It reports **API usage
correctness**. It does **not** report:

- whether rendered output is visually correct,
- whether CPU-side logic or test suites pass,
- GPU performance numbers (use the profiler capture harness or a GPU profiler),
- driver-internal correctness. No findings means none of the layer's checks fired for
  the exercised workload — not certification of spec compliance or rendered correctness.

Validation adds meaningful per-call CPU overhead. Treat it as a development-only aid:
enable it for dedicated test runs, not normal play. Mods shipped to users do not depend
on it.

## Installed layer (this machine, this user)

- Layer: `VK_LAYER_KHRONOS_validation`, from the LunarG Vulkan SDK, installed per-user
  by file copy (no admin, no PATH or machine-wide changes).
- SDK root: `C:\Users\AMPW\AppData\Local\VulkanValidationLayers\<version>\SDK`
- Manifest: `...\SDK\Bin\VkLayer_khronos_validation.json`
- Registration: `HKCU\SOFTWARE\Khronos\Vulkan\ExplicitLayers`, value name = the absolute
  manifest path, `DWORD 0`. Discoverable by every process of this Windows account, but
  only engages for processes that request it.

Confirm discoverability before a run:

```powershell
vulkaninfo --summary   # VK_LAYER_KHRONOS_validation must appear under Instance Layers
```

## Per-run launch recipe

Every run needs an isolated instance directory prepared beforehand (see `ksa-launch` for
the required `manifest.toml` + `mods/<ModId>/` layout; mod repos may provide their own
staging target). The instance's own `manifest.toml` decides which mods load. Each run
gets a fresh evidence directory so validation output is never overwritten.

```powershell
# --- user input: an existing isolated instance directory ---
$instancePath = 'C:\path\to\your\isolated\instance'
$starMapExe   = "$env:USERPROFILE\Documents\My Games\Kitten Space Agency\mods\StarMap\StarMap.exe"

# --- fail fast if the instance, its manifest, or the launcher is missing ---
if (-not (Test-Path $instancePath))                             { throw "instance not found: $instancePath" }
if (-not (Test-Path (Join-Path $instancePath 'manifest.toml'))) { throw "manifest.toml missing in $instancePath" }
if (-not (Test-Path $starMapExe))                               { throw "launcher not found: $starMapExe" }

# --- unique per-run evidence directory (fails instead of overwriting) ---
$runDir = Join-Path $env:LOCALAPPDATA (
    'VulkanValidationLayers\runs\{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'),
    [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $runDir -ErrorAction Stop | Out-Null

# --- validation settings for THIS run; VK_LAYER_SETTINGS_PATH selects the directory ---
@(
    'khronos_validation.validate_sync = true',
    'khronos_validation.debug_action = VK_DBG_LAYER_ACTION_LOG_MSG',
    "khronos_validation.log_filename = $runDir\vvl-messages.log",
    'khronos_validation.report_flags = error,warn,perf,info'
) | Set-Content -Path (Join-Path $runDir 'vk_layer_settings.txt')

# --- remember any pre-existing process-level values so we restore, not erase ---
$names = 'STARMAP_INSTANCE_PATH','VK_INSTANCE_LAYERS','VK_LAYER_SETTINGS_PATH','VK_LOADER_DEBUG'
$saved = @{}
foreach ($n in $names) { $saved[$n] = [Environment]::GetEnvironmentVariable($n, 'Process') }

$stdoutLog = Join-Path $runDir 'stdout.log'
$stderrLog = Join-Path $runDir 'stderr.log'

try {
    $env:STARMAP_INSTANCE_PATH  = $instancePath
    $env:VK_INSTANCE_LAYERS     = 'VK_LAYER_KHRONOS_validation'
    $env:VK_LAYER_SETTINGS_PATH = $runDir
    $env:VK_LOADER_DEBUG        = 'warn,error,info'

    # Optional: enable mod-specific diagnostic env vars here if the mod documents them.

    Start-Process -FilePath $starMapExe `
        -WorkingDirectory (Split-Path $starMapExe -Parent) `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError  $stderrLog `
        -Wait
}
finally {
    foreach ($n in $names) {
        if ($null -eq $saved[$n]) { Remove-Item "Env:\$n" -ErrorAction SilentlyContinue }
        else { [Environment]::SetEnvironmentVariable($n, $saved[$n], 'Process') }
    }
}

Write-Output "Run evidence: $runDir"
```

All variable changes are process-scoped and restored in `finally`; nothing is written to
the user or machine environment, the registry, or any mod manifest. `StarMap.exe` is
launched from its own directory because mods load through the StarMap launcher, not
`KSA.exe`.

## Reading the evidence

After the app has actually created its Vulkan instance and run a workload, check
`vvl-messages.log` in the run directory:

```powershell
# activation record: emitted once per VkInstance when 'info' severity is enabled
Select-String -Path .\vvl-messages.log -Pattern 'CURRENT-VALIDATION-ENABLED'
# confirms synchronization validation is among the active checks
Select-String -Path .\vvl-messages.log -Pattern 'Synchronization'
# actual findings (no assumptions about count or absence)
Select-String -Path .\vvl-messages.log -Pattern 'Validation Error|Validation Warning|SYNC-HAZARD|VUID-'
```

The `CURRENT-VALIDATION-ENABLED` record is the runtime proof that the layer engaged.
Its absence is not definitive proof the layer never engaged (`info` severity or log
routing could be misconfigured) — investigate `VK_INSTANCE_LAYERS`, the registry entry,
and that the process really used Vulkan before trusting the rest of the log.
`stderr.log` additionally shows `VK_LOADER_DEBUG` lines such as `Insert instance layer`.

Interpretation cautions:

- A log with no findings certifies only that **none of the layer's checks fired for the
  exercised workload** — not spec compliance and not visual correctness. Exercise the
  code paths you care about; an idle launcher proves little.
- `enable_message_limit` suppresses repeats — matching-line counts are **not** true
  message frequency.
- An **orderly exit matters**: resource-lifetime and leak checks largely run at
  `vkDestroy*`/`vkDestroyDevice` time, so a killed process yields incomplete evidence.
- Loader duplicate-layer warnings and the application's own startup messages are **not**
  validation findings — attribute anything suspicious against an isolated baseline run
  under a matching workload.
- The baseline keeps the **same validation settings active**; it excludes only the mod
  under test — not the layer. Baseline and modded runs need the same launch procedure
  and workload.

## Removal

Only unregister the layer if it should no longer be offered to any mod on this account.
Keep the installed files and run logs — they are the provenance record and evidence
store. Remove exactly the one registry value for the manifest path; do not delete the
`ExplicitLayers` key itself — other registrations may live under it.

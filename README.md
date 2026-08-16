# besthttp-system-proxy — make BestHTTP apps use your system proxy (IPA patch)

> [日本語版はこちら / Read this in Japanese](README.ja.md)

Patches apps that talk to their servers **directly** through Unity's
**BestHTTP** so they read the **manual HTTP proxy** configured in iOS Wi-Fi
settings instead. No jailbreak required; works with IPAs you side-load via
Sideloadly, PlayCover, and friends.

## How it works

`ProxyRedirect.dylib` is a tiny library with only a
`__attribute__((constructor))`. It runs the moment the app launches (before
any Unity/IL2CPP code) and:

1. reads the OS manual HTTP proxy via `CFNetworkCopySystemProxySettings()`
2. converts it to `http://host:port` (IPv6 literals become `[::1]:port`)
3. exports `http_proxy` / `https_proxy` / `HTTP_PROXY` / `HTTPS_PROXY`
   (both lowercase and uppercase variants)

BestHTTP's `EnvironmentProxyDetector` reads these environment variables at
startup, so all subsequent traffic goes through the system proxy (HTTPS via
CONNECT). There are no function hooks and no IL2CPP dependencies — the app
binary is otherwise untouched.

### Override file (optional)

On systems where the iOS proxy settings aren't available (e.g. PlayCover /
macOS), write a file at `<App>/Documents/proxy_override.txt` containing

```
192.168.10.17:8888
```

and it takes precedence over the system settings.

### Log

On launch the used proxy is recorded in
`<App>/Documents/proxy_redirect.log`:

```
[ProxyRedirect] using system proxy
[ProxyRedirect] proxy -> http://192.168.10.17:8888
```

## Usage

```bash
# 1. Build the dylib (Xcode Command Line Tools only, no Python needed)
make                          # -> out/ProxyRedirect.dylib

# 2. Patch an IPA
python3 tools/pack_ipa.py MyGame.ipa
# -> MyGame_proxy.ipa next to the input (use --output to choose a path)

# 3. Install
#    Real device: side-load with Sideloadly, then set a manual proxy in Wi-Fi
#    settings.
#    PlayCover: before launching, write "host:port" into
#    Documents/proxy_override.txt.
```

```bash
python3 tools/pack_ipa.py MyGame.ipa --output out/MyGame_proxy.ipa --no-sign
```

The pipeline: extract to `work/` → add an `LC_LOAD_DYLIB` entry to the main
binary (`tools/insert_load_dylib.py`, thin arm64 Mach-O only) → ad-hoc sign →
re-zip preserving symlinks. The input IPA is never modified.

## Requirements

- macOS with Xcode Command Line Tools (`clang`, `xcrun`, `codesign`)
- Python 3.9+ on the host (for `pack_ipa.py`)

## Limitations

- Thin **arm64 Mach-O only** (thin universal binaries first with
  `lipo -thin arm64`).
- Assumes BestHTTP's `EnvironmentProxyDetector` reads environment variables;
  if the app disables proxy detection itself, another approach is needed.
- Intended for reverse-engineering / offline use of games you own.
  Use at your own risk.

## License

MIT — see [LICENSE](LICENSE).

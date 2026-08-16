# besthttp-system-proxy — BestHTTP の通信をシステムプロキシ経由にする IPA パッチ

> [English version / 英語版はこちら](README.md)

Unity の **BestHTTP** を使ってサーバーへ直接接続しているアプリを、
iOS の Wi-Fi 設定で構成した **手動 HTTP プロキシ** を読むように書き換えます。
Jailbreak 不要。Sideloadly / PlayCover などでサイドロードできる IPA を
そのままパッチします。

## 仕組み

`ProxyRedirect.dylib` は `__attribute__((constructor))` を持つだけの小さな
ライブラリです。アプリ起動の瞬間（Unity/IL2CPP のコードが動く前）に実行され:

1. `CFNetworkCopySystemProxySettings()` で OS の手動 HTTP プロキシを読み取る
2. `http://host:port` 形式に変換（IPv6 リテラルは `[::1]` 形式に対応）
3. `http_proxy` / `https_proxy` / `HTTP_PROXY` / `HTTPS_PROXY` 環境変数に
   両方の大文字小文字で書き出す

BestHTTP の `EnvironmentProxyDetector` は起動時に環境変数を読むため、
以降の通信はすべてシステムプロキシを通ります（HTTPS も CONNECT 経由）。
関数フックや IL2CPP への依存はなく、環境変数の書き出しだけなので
アプリ本体には一切手を入れません。

### 上書きファイル（任意）

システム設定が読めない環境（PlayCover/macOS など）では、
アプリの `Documents/proxy_override.txt` に

```
192.168.10.17:8888
```

と書くと、そのプロキシが OS 設定より優先されます。

### ログ

起動時に `Documents/proxy_redirect.log` へ使用したプロキシを記録します:

```
[ProxyRedirect] using system proxy
[ProxyRedirect] proxy -> http://192.168.10.17:8888
```

## 使い方

```bash
# 1. dylib をビルド（Xcode Command Line Tools のみ、Python 不要）
make                          # -> out/ProxyRedirect.dylib

# 2. IPA をパッチ
python3 tools/pack_ipa.py MyGame.ipa
# -> MyGame_proxy.ipa が生成（--output でパス指定可）

# 3. インストール
#    実機: Sideloadly などでサイドロード後、Wi-Fi 設定に手動プロキシを設定
#    PlayCover: 起動前に Documents/proxy_override.txt に "host:port" を書く
```

```bash
python3 tools/pack_ipa.py MyGame.ipa --output out/MyGame_proxy.ipa --no-sign
```

パッチは `work/` に解凍 → メインバイナリに `LC_LOAD_DYLIB` を追加
（`tools/insert_load_dylib.py`、シン arm64 Mach-O のみ）→ ad-hoc 署名 →
シンボリックリンク保持で再 zip、という流れです。入力 IPA は変更しません。

## 必要なもの

- macOS + Xcode Command Line Tools（`clang`, `xcrun`, `codesign`）
- Python 3.9+（`pack_ipa.py` 用）

## 制限

- シン arm64 Mach-O のみ対応（ユニバーサルバイナリは `lipo -thin arm64` で
  thin 化してください）
- BestHTTP の `EnvironmentProxyDetector` が環境変数を読む前提です。
  アプリ側でプロキシ検出が無効化されている場合は別の方法が必要です
- 本ツールはオフラインゲームのリバースエンジニアリング用途です。
  利用は自己責任で

## ライセンス

MIT

# Reddit VOC Local Bridge 1.0.0-rc1 offline gate

Run date: 2026-09-16. Chrome was not opened and Reddit was not accessed.

| Gate | Result |
|---|---|
| Python full suite | PASS — 86/86 |
| JavaScript full suite | PASS — 15/15 |
| Extension/bridge focused tests | PASS — JS 11/11, Python 6/6 |
| Every extension JavaScript `node --check` | PASS |
| Bridge `py_compile` | PASS |
| Manifest 1.0.0-rc1 parse and exact permission contract | PASS |
| Forbidden permission/API scan | PASS |
| Skill `quick_validate.py` | PASS |
| Offline bridge startup / fixed ID / 32-char RUN_ID | PASS |
| Bridge shutdown / port 43127 closed | PASS |

The tests cover unmarked-page early exit, marked search idle, marked post capture, same-run post switching, non-Reddit rejection, wrong RUN_ID, wrong extension ID/Origin, exact CORS, no tab enumeration, recursive multi-control expansion, continue-thread traversal, multiple depths, filtering, dedupe, parent/depth preservation, checkpoint persistence, HMAC verification, session expiry, stale timestamp, nonce replay, bridge-stop fuse, body limits and absence of session keys on disk.

## SHA-256

```text
7fb285e6d7b0a544222234889d6266cef058b53874df665d87543f5d44315285  extension\manifest.json
a38e28cc34d269cc8a3e56791f0f63f76446142c35b5656eefaa63ad7490b503  extension\capture_core.js
4b38c6b1a6f6b2dce47894716f52f45c3ff6f976dd4fb1142b8beb62919f5c83  extension\session_core.js
b4cb390664c4fb2fa48edded3473a2789c079dd7fa41734cf0c907c808ab2dcb  extension\service_worker.js
62671f7d1ede405122db421a5d4ac27d0c3e0f61428cdf9e9940939cd1e066cc  extension\visible_capture.js
49125331fc01ed6294de56c8295b9173f5c316dda341fd2eef8d525cf10aa688  extension\auto_content.js
67e62f500a784ff8fa1b7a1663ae5d63826db6792250ec2f58cf9e673ac117bd  local_bridge\reddit_bridge_server.py
af0f2e0963ef0826efe080f77231b03fa9cde71b01f20215bd490a00be8bd7ac  tests\test_extension_bridge.cjs
ec14e88c11ccd2740b2b38a6e404c647a924f68f1f27a310ae241fb3b34854b0  tests\test_extension_bridge_security.py
```

The next gate is one manual Chrome reload of the already-loaded unpacked extension. After reload, smoke execution requires no popup click, pairing-code entry or per-post authorization.

# Security policy

## Reporting a vulnerability

Please **don't open a public issue** for security problems. Report them privately through GitHub: on the repository's **Security** tab, choose **Report a vulnerability** (or go to <https://github.com/mathiasdbo/Frametime-analyzer-tool/security/advisories/new>).

Include what you found, how to reproduce it, and what an attacker could do with it. You'll get a reply as soon as possible.

## Scope notes

- The browser Studio (`fta studio`) is a local tool: it can open files from disk and has no authentication. It listens on `127.0.0.1` by default. Exposing it on a network with `--host 0.0.0.0` is at your own risk.
- Only the latest release receives fixes.

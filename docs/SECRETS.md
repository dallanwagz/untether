# Handling secrets — keep what your validation needs, safely (never in git)

"Redact secrets" (a [contribution non-negotiable](../CONTRIBUTING.md)) is only half the story. The
other half: ongoing RE/validation often *does* need a credential or two (an HA long-lived token, a
device key). Keep those **encrypted at rest and out of git** — not in a repo, not even a private one.

## What is / isn't a secret

| Treat as a **secret** (never commit) | **Not** secret (fine in profiles/notes) |
|---|---|
| HA long-lived tokens | BLE MAC addresses |
| Vendor cloud account tokens / passwords | GATT service & characteristic UUIDs |
| Wi-Fi / OAuth credentials | RFCOMM channel numbers |
| Device passwords / pairing keys | Manufacturer / company IDs, local-name prefixes |
| API keys | Golden frames (with secrets scrubbed) |

If a captured frame or JSON path *carries* a secret, note its presence and **redact the value** —
don't paste it (see the Divoom/Govee profiles for examples).

## The anti-pattern: don't aggregate plaintext secrets into a repo

Pushing secrets to git — **even a private repo** — moves them from *more* protected to *less*:
they replicate to the remote and every clone, persist in history forever (deleting the file later
doesn't scrub past commits), and are one visibility-flip or account compromise from exposure.
Plaintext-in-git is one of the most common real-world credential leaks. Don't do it. Local,
encrypted, access-controlled storage beats a remote git host for secrets.

## Recommended: macOS Keychain (single machine)

Store / update (the value lives only in the Keychain):
```sh
security add-generic-password -a "$USER" -s myproject-ha-token -w "<token>" -U
security add-generic-password -a "$USER" -s myproject-ha-url   -w "<url>"   -U
```
Read one back (prints the value — only when you mean to):
```sh
security find-generic-password -a "$USER" -s myproject-ha-token -w
```
Generic loader for your scripts (Keychain first, env/config fallback so nothing breaks):
```python
import getpass, os, subprocess

def keychain(service):
    r = subprocess.run(
        ["security", "find-generic-password", "-a", getpass.getuser(), "-s", service, "-w"],
        capture_output=True, text=True)
    return r.stdout.strip() or None if r.returncode == 0 else None

def load_ha():
    token = keychain("myproject-ha-token") or os.environ.get("HOMEASSISTANT_TOKEN")
    url = keychain("myproject-ha-url") or os.environ.get("HOMEASSISTANT_URL", "")
    if not token:
        raise RuntimeError("HA token not in Keychain or env")
    return url.rstrip("/"), token
```

## Recommended: `sops` + `age` or `git-crypt` (a team / a repo you want versioned)

If you genuinely want secrets *versioned alongside code*, encrypt them at rest so the repo only ever
holds ciphertext:
- **[`sops`](https://github.com/getsops/sops) + [`age`](https://github.com/FiloSottile/age)** —
  per-file encryption; commit the encrypted file, share the `age` key out-of-band.
- **[`git-crypt`](https://github.com/AGWA/git-crypt)** — transparent encryption of paths matched in
  `.gitattributes`.

Either way the plaintext never enters a commit. A password manager (1Password, Bitwarden) or a
cloud KMS/secrets-manager works too.

## Rule of thumb

Commit the **map** (MACs, UUIDs, channels, scrubbed golden frames). Keep the **keys** (tokens,
passwords) in Keychain / an encrypted vault. If you're about to `git add` something you'd be unhappy
to see on a public mirror, stop — that's a secret, and it belongs in the vault.

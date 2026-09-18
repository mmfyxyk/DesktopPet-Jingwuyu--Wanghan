# Jingwuyu — Wanghan Desktop Pet 🐾

> A desktop companion of **Wanghan (Jingwuyu)** roaming on your Windows screen.
>
>(All documents are in old versions.Please be patient and wait for updates. Sorry for the inconvenience)
>
> Supports 10 pet states (idle, walking, sleeping, eating, angry…), left-button drag-and-drop, a right-click feed menu, and optional Bilibili / Douyin crawlers that check for the latest videos.

<br>

<p align="center">
  <b>
    <a href="#download-and-install">💾 Download</a>
    ·
    <a href="#quick-start">⚡ Quick Start</a>
    ·
    <a href="#feature-overview">🎮 Features</a>
    ·
    <a href="#faq">💡 FAQ</a>
    ·
    <a href="README.md">🇨🇳 中文</a>
  </b>
</p>

<br><br>

---

## 💾 Download and Install

### 📦 Three distribution builds — pick one

| Build | File name | For whom | How to run |
|---|---|---|---|
| **Portable (recommended)** | `DesktopPet-Portable-<version>.zip` | No installer, run anywhere | Extract anywhere → double-click **「启动宠物.bat」** (or `pet.exe`) |
| **Setup installer** | `DesktopPet-Setup-<version>.exe` | Normal install, Start Menu / desktop shortcut / auto-start | Run the wizard; pick any install folder (default: `C:\Program Files\DesktopPet`) |
| **Source code** | `DesktopPet-Source-<version>.zip` | Hacking, forking, building from source | See *"Developer quick start"* below |

### 🔗 Direct download links (Release pages)

| Host | URL |
|---|---|
| **GitHub** (global / CDN-friendly) | [github.com/mmfyxyk/DesktopPet-Jingwuyu--Wanghan/releases](https://github.com/mmfyxyk/DesktopPet-Jingwuyu--Wanghan/releases) |
| **Gitee** (faster for users in China) | [gitee.com/mmfyxyk/DesktopPet-Jingwuyu--Wanghan/releases](https://gitee.com/mmfyxyk/DesktopPet-Jingwuyu--Wanghan/releases) |

> 🟡 **Windows SmartScreen may warn "Unknown publisher"** after download — click *"More info" → "Run anyway"*. This project does **not** purchase a code-signing certificate to keep costs down for a personal app. Functionality is not affected.

### System requirements
- Windows 10 (1903+) / Windows 11 — 64-bit
- At least 2 GB of free disk space (Qt6 runtime + bundled deps ≈ 600 MB; additional space for crawler downloads)
- First run opens a *Terms and Disclaimer* dialog. Please read to the bottom and wait for the countdown before you can continue.

<br><br>

---

## ⚡ Quick Start

### ▶️ Launch
- **Portable**：double-click `启动宠物.bat` in the extracted folder (or run `pet.exe` directly)
- **Installed**：click the *「桌面电子宠物」* desktop shortcut, or find it in the Start Menu.

A tiny Wanghan will appear near the bottom-right of your screen and start her wandering life 😇.

### 🖱 Basic interaction

| Action | Effect |
|---|---|
| **Left-click & drag** (> 5 px) | Pick up the pet, drop her anywhere on the desktop |
| **Left-click** (tap) | Small happy / response animation |
| **Right-click** the pet | Opens the main menu (Eat / Ask for food / Feed user / Extras / Settings / About this project / Quit) |
| **Release after dragging** | Plays a *"land bounce"* transition animation |

### 🍜 Feeding flow
1. Right-click → **Ask for food** → a grape juice image pops up next to her.
2. Click or drag the grape juice onto the pet → she drinks it, then coughs up a piece of tofu 🧊 for you.
3. The tofu image sits on the desktop for a few seconds — you can drag it away any time.

### 📺 Extras (Bilibili / Douyin)
Right-click → **Extras ▶**
- **Crawl latest Bilibili videos** — fetch new uploads on the Bilibili space.
- **Douyin ▶ Crawl latest Douyin videos** — fetch new posts on the Douyin profile page.
- **Douyin ▶ Sign in / Re-sign in (QR scan)** — Do this **before first use**. Login state is persisted locally on your PC.
- **Douyin ▶ Clear login data (Sign out)** — remove Douyin login state from all 3 locations (with confirmation).
- **Proxy settings…** — HTTP / SOCKS5h + optional auth for the Bilibili / Douyin crawlers.
- **Clear private data…** — choose which local proxy config / Douyin login / Chrome profile / display settings cache to wipe.
- **Open data dir / Open output dir** — jump straight to crawler cache or final download folders in Explorer.

### ⚙ Settings
Right-click → **Settings ▶**
- **Always on top** (checkable toggle). On by default. Turn it off so your game / movie / full-screen meeting can cover the pet.
- **Adjust pet size…** — height range 120~480 px, three preset buttons: **Small 180 / Medium 240 (default) / Large 320**. Bone / grape-juice / tofu items auto-scale along with pet height.
- **Reset to defaults** — one-click back to *Always on top = on, Height = 240 px* (confirmation dialog; never touches crawler data).

> Every change is saved automatically to `data/settings.json` — **it survives app restarts**.

### 📌 About this project
Right-click → **About this project ▶**
- **GitHub / Gitee**：Open the Releases / repository page.
- **ihan fan site ✨**：Easter egg — opens ihan.com.cn in your browser.

<br><br>

---

## 🎮 Feature Overview

| Module | What it does |
|---|---|
| 🧸 Pet FSM | 10 states: IDLE / WALKING / DRAGGING / EATING / ASKING\_FOOD / FEEDING / SLEEPING / PLAYING / ANGRY / RELEASED |
| 🖼 Transparent overlay | Frameless window, fully transparent background — only the character sprite is visible; always-on-top **by default**, toggle it off from *Settings → Always on top* when watching shows / playing games |
| 🎨 Autoscale | Sprites scale proportionally to a unified height with no window jumping; *Settings → Adjust pet size…* lets you customize live between 120~480 px. |
| 📜 First-run disclaimer | Must scroll to bottom + sit through a countdown before you can continue (clearly personal & non-commercial posture) |
| 📹 Bilibili crawler | Local WBI signature algorithm, Selenium fallback for protected pages |
| 🎵 Douyin crawler | QR-code login, state persisted in 3 places (Chrome Profile + Cookie JSON + Netscape TXT), downloads handled by yt-dlp. One-click "clear login data" in the menu. |
| 🔐 Privacy toolbox | *Extras → Clear private data… / Open data dir / Open output dir* — inspect and clean everything the app wrote to your disk locally. Nothing phones home. |
| 🌐 Proxy settings | HTTP / SOCKS5h + optional auth (*Extras → Proxy settings…*) for Bilibili / Douyin crawlers |
| 📦 Distribution | 3 artifacts: Portable ZIP / Setup EXE / Source ZIP — all produced by one build script |

<br><br>

---

## 💡 FAQ

**Q: SmartScreen says "Unknown publisher" when I try to launch?**
A: Expected. This project does not ship with an EV code-signing certificate. Click *More info → Run anyway*. It's safe.

**Q: The pet shows a blank image after extracting the portable build?**
A: Please don't move or rename `_internal/` and `assets/` under the extracted folder. If it still shows blank, re-extract or re-download the same version from Releases.

**Q: Douyin / crawler actions do nothing?**
A: Run *"Extras → Douyin → Sign in / Re-sign in (QR scan)"* first. The login state persists long-term. If it still fails, check *Extras → Proxy settings…* or your local network.

**Q: When I uninstall, will my data be kept?**
A: **By default: yes.** Right before uninstall finishes, a confirmation dialog asks *"Also delete user data under data/ output/ support/Chrome?"* and defaults to *No* — so re-installing later keeps your login state and downloaded videos intact.

**Q: I want to build from source / modify the app?**
A: Download the *Source* zip or `git clone`, Python 3.13+ required:
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Build all three release artifacts with: `python scripts/build_all.py --version 1.0.0`

<br><br>

---

## 📌 Legal & Copyright notice

- This software is a personal, open-source, non-commercial project released under the [MIT License](LICENSE).
- All rights to character names and likenesses (**Wanghan / Jingwuyu**) belong to their respective copyright holders. Please keep the app for personal entertainment only. **Any commercial use or redistribution beyond fair use requires prior written permission** from the rights holder(s).
- When using the crawler modules, please respect the Terms of Service, User Agreement, and Privacy Policy of the target platforms (Bilibili, Douyin), and use them lawfully and reasonably so as not to cause unnecessary access pressure.

<br><br>

---

## 🤝 License

- Source code: [MIT License](LICENSE) — © 2026 锐尘/ruichen
- Design docs (Chinese): [docs/Desktop pet frame v3.md](docs/Desktop%20pet%20frame%20v3.md)

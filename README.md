# MP3 Studio

A desktop app to edit MP3 metadata, auto-fetch album art & lyrics, and apply EQ before exporting — so your tracks look and sound great in Apple Music.

![Python](https://img.shields.io/badge/python-3.10+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Metadata editor** — Title, Artist, Album, Year, Genre
- **Album art** — upload your own image or auto-fetch from iTunes
- **Lyrics** — auto-fetch from Lyrics.ovh, or paste your own
- **5-Band EQ** — Bass / Low Mid / Mid / High Mid / Treble (±12 dB each)
- **Extra effects** — Normalize volume, Stereo enhance, Playback speed
- **Batch queue** — load multiple MP3s and switch between them
- **Non-destructive** — EQ is only applied on Export; Save Metadata edits tags in-place

---

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/download.html) — required by pydub for audio processing

### Install ffmpeg

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html and add the `bin` folder to your PATH.

**Linux (apt):**
```bash
sudo apt install ffmpeg
```

---

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/mp3-studio.git
cd mp3-studio
pip install -r requirements.txt
python app.py
```

That's it. No API keys needed.

---

## How to use

1. Click **+ Add MP3 Files** and pick your songs
2. Select a song from the queue on the left
3. Fill in Artist & Title if not already detected from the filename
4. Hit **Auto Fetch All** — pulls album art, album name, year, genre, and lyrics automatically
5. Tweak anything manually (upload your own art, edit lyrics, etc.)
6. Click **Save Metadata** to write tags directly to the MP3
7. Drag the file into Apple Music — it will now show artwork and lyrics

### EQ / Export

1. Go to the **Audio EQ** tab
2. Adjust the 5 EQ sliders (drag up = boost, down = cut)
3. Optionally enable Normalize, Stereo Enhance, or change Speed
4. Click **Export MP3** — saves a new 320 kbps file with EQ applied + metadata embedded

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `pydub` can't read MP3 | Install ffmpeg and make sure it's in PATH |
| Lyrics not found | The song may not be in lyrics.ovh's database — paste manually |
| Album art not found | Try correcting the Artist/Title spelling first |

---

## License

MIT

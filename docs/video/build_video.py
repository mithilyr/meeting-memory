"""Assemble the walkthrough video from the voiceover clips, screen clips, title cards and callouts.

    python docs/video/build_video.py                       # uses docs/video/audio and docs/video/screen
    python docs/video/build_video.py --audio A --screen S --out walkthrough.mp4

audio/01.mp3 .. 09.mp3    one ElevenLabs clip per voiceover section (voiceover.md)
screen/01.mp4 .. 09.mp4   one screen recording per section, any length: it is cut to the voice, and the
                          last frame is held if it is shorter. A missing clip shows the section's card.

Each section is its title card (2.5 s, silent), then the screen clip with the voice and that section's
callouts laid over it. Needs ffmpeg and ffprobe on PATH.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CARD_SECONDS = 2.5
TITLE_SECONDS = 3.0
W, H, FPS = 1920, 1080, 30
#: section -> [(callout file, start as a share of the voice, seconds shown)]
#: Slides (sections 2 and 8) already state their numbers on screen, so they get no callout.
CALLOUTS = {
    3: [("b-current.png", 0.35, 5)],
    4: [("c-quotes.png", 0.55, 5)],
    5: [("d-no.png", 0.60, 5)],
    6: [("e-cutoff.png", 0.55, 5)],
    7: [("f-audit.png", 0.78, 5)],
}
END_HOLD = 1.5  # seconds of quiet on the last frame before the video ends
VIDEO = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS)]
AUDIO = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def run(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def fit(label: str) -> str:
    """Scale any input to 1920x1080 on the app's black, without stretching."""
    return (f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0B0B0C,"
            f"fps={FPS},format=yuv420p{label}")


def still(image: Path, seconds: float, out: Path) -> None:
    """A card on screen with silence, so every segment has the same streams for joining."""
    run(["-loop", "1", "-t", str(seconds), "-i", str(image), "-f", "lavfi", "-t", str(seconds),
         "-i", "anullsrc=r=48000:cl=stereo", "-vf", fit(""), *VIDEO, *AUDIO, "-shortest", str(out)])


def body(n: int, card: Path, screen: Path | None, voice: Path, out: Path, hold: float = 0.0) -> None:
    length = duration(voice) + hold
    inputs = (["-i", str(screen)] if screen else ["-loop", "1", "-i", str(card)]) + ["-i", str(voice)]
    chain = f"[0:v]{fit('')},tpad=stop_mode=clone:stop_duration=600,trim=duration={length:.3f},setpts=PTS-STARTPTS[v0]"
    last = "v0"
    for i, (name, share, shown) in enumerate(CALLOUTS.get(n, []), start=1):
        inputs += ["-loop", "1", "-i", str(HERE / "callouts" / name)]
        start = share * length
        chain += (f";[{i + 1}:v]format=rgba,fade=in:st={start:.2f}:d=0.3:alpha=1,"
                  f"fade=out:st={start + shown - 0.3:.2f}:d=0.3:alpha=1[c{i}]"
                  f";[{last}][c{i}]overlay=0:0:enable='between(t,{start:.2f},{start + shown:.2f})'[v{i}]")
        last = f"v{i}"
    chain += ";[1:a]apad[a]"  # silence after the voice fills any hold
    run([*inputs, "-filter_complex", chain, "-map", f"[{last}]", "-map", "[a]", "-t", f"{length:.3f}",
         *VIDEO, *AUDIO, str(out)])


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble the walkthrough video.")
    parser.add_argument("--audio", default=str(HERE / "audio"))
    parser.add_argument("--screen", default=str(HERE / "screen"))
    parser.add_argument("--out", default=str(HERE / "walkthrough.mp4"))
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is not on PATH")
    audio, screens = Path(args.audio), Path(args.screen)
    cards = sorted((HERE / "cards").glob("*.png"))
    with tempfile.TemporaryDirectory() as tmp:
        parts = [Path(tmp) / "00.mp4"]
        still(cards[0], TITLE_SECONDS, parts[0])
        for n in range(1, 10):
            voice = next(iter(sorted(audio.glob(f"{n:02d}.*"))), None)
            if voice is None:
                print(f"section {n}: no voice clip in {audio}, skipped")
                continue
            card = next(c for c in cards if c.name.startswith(f"{n:02d}-"))
            screen = next(iter(sorted(screens.glob(f"{n:02d}.*"))), None) if screens.is_dir() else None
            still(card, CARD_SECONDS, Path(tmp) / f"{n:02d}a.mp4")
            body(n, card, screen, voice, Path(tmp) / f"{n:02d}b.mp4", END_HOLD if n == 9 else 0.0)
            parts += [Path(tmp) / f"{n:02d}a.mp4", Path(tmp) / f"{n:02d}b.mp4"]
            print(f"section {n}: {duration(voice):.1f} s of voice, {'screen clip' if screen else 'card only'}")
        listing = Path(tmp) / "parts.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        run(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", args.out])
    total = duration(Path(args.out))
    print(f"wrote {args.out}: {total // 60:.0f} min {total % 60:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

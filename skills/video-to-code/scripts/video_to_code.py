"""YouTube tutorial -> screenshots + transcript + the code shown on screen.

Folder written under the destination chosen by the user:

    <destino>/<Titulo do video>/
    ├── README.md            written by the agent (step-by-step guide)
    ├── CONFERENCIA.md       written by the agent (code file -> source frames)
    ├── transcricao.md       speech with [hh:mm:ss] marks
    ├── codigo/              written by the agent (runnable project)
    ├── screenshots/         frames used in README.md
    ├── conferencia/         frames each code file was transcribed from
    ├── video/               <titulo>.mp4, .info.json, subtitles
    └── _trabalho/           frames/, contact/, frames.json, transcripts/ (cache)

Usage:
    python video_to_code.py destino [--set <pasta>]          # last destination (JSON)
    python video_to_code.py baixar <url> --destino <pasta>     # download + metadata (JSON)
    python video_to_code.py frames <pasta_video> [--every 2] [--screen 0.35] [--step 0.03]
    python video_to_code.py transcrever <pasta_video> [--language pt] [--engine auto] [--legenda]
    python video_to_code.py frame <pasta_video> --at 12:34 [--at 1:02:03] [--into conferencia/x]
    python video_to_code.py crop <imagem> --box x,y,w,h [--scale 2] [-o saida.png]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))

from videokit.cli import run_main  # noqa: E402
from videokit.media import VIDEO_EXTS, capture, probe  # noqa: E402

CONFIG = Path.home() / ".config" / "video-skills" / "config.json"
WORK = "_trabalho"


def dump(obj) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def hms(t: float, sep: str = ":") -> str:
    t = int(max(t, 0))
    return f"{t // 3600:02d}{sep}{t % 3600 // 60:02d}{sep}{t % 60:02d}"


def parse_time(s: str) -> float:
    parts = [float(p) for p in s.strip().split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def safe_name(title: str) -> str:
    title = unicodedata.normalize("NFC", title)
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    title = re.sub(r"\s+", " ", title).strip(" .")
    return title[:90].rstrip(" .") or "video"


def find_video(folder: Path) -> Path:
    folder = folder.resolve()
    if folder.is_file():
        return folder
    vids = sorted(p for p in (folder / "video").glob("*") if p.suffix.lower() in VIDEO_EXTS)
    if not vids:
        sys.exit(f"nenhum vídeo em {folder / 'video'} (rode 'baixar' antes)")
    return vids[0]


def project_dir(video_or_folder: Path) -> Path:
    p = video_or_folder.resolve()
    return p.parent.parent if p.is_file() else p


# ---------------------------------------------------------------- destino

def cmd_destino(args) -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    if args.set:
        dest = Path(args.set).expanduser().resolve()
        dest.mkdir(parents=True, exist_ok=True)
        cfg["video_to_code_destino"] = str(dest)
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    dest = cfg.get("video_to_code_destino")
    dump({"destino": dest, "existe": bool(dest and Path(dest).is_dir())})


# ---------------------------------------------------------------- baixar

def yt_dlp() -> list[str]:
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        sys.exit("yt-dlp não encontrado: pip install -U yt-dlp")


def cmd_baixar(args) -> None:
    base = yt_dlp()
    r = subprocess.run([*base, "-J", "--no-playlist", args.url], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"yt-dlp não conseguiu ler o vídeo:\n{r.stderr[-1500:]}")
    meta = json.loads(r.stdout)
    title = meta.get("title") or meta.get("id") or "video"
    folder = Path(args.destino).expanduser().resolve() / safe_name(args.nome or title)
    vdir = folder / "video"
    vdir.mkdir(parents=True, exist_ok=True)

    existing = [p for p in vdir.glob("*") if p.suffix.lower() in VIDEO_EXTS]
    if existing:
        print(f"  já baixado: {existing[0].name}", flush=True)
    else:
        h = args.max_height
        cmd = [*base, "--no-playlist",
               "-f", f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/bv*[height<={h}]+ba/b[height<={h}]/b",
               "--merge-output-format", "mp4",
               "--write-info-json", "--write-subs", "--write-auto-subs",
               "--sub-langs", args.sub_langs, "--sub-format", "vtt", "--ignore-errors",
               "--windows-filenames", "-o", str(vdir / "video.%(ext)s"), args.url]
        print(f"  baixando ({h}p máx.)...", flush=True)
        dl = subprocess.run(cmd)
        if not any(p.suffix.lower() in VIDEO_EXTS for p in vdir.glob("*")):
            sys.exit(f"download falhou (yt-dlp saiu com {dl.returncode})")

    video = find_video(folder)
    info = probe(video)
    chapters = [{"inicio": hms(c["start_time"]), "fim": hms(c["end_time"]), "titulo": c.get("title")}
                for c in meta.get("chapters") or []]
    subs = sorted(p.name for p in vdir.glob("*.vtt"))
    (folder / WORK).mkdir(exist_ok=True)
    dump({
        "pasta": str(folder),
        "video": str(video),
        "titulo": title,
        "canal": meta.get("channel") or meta.get("uploader"),
        "url": meta.get("webpage_url") or args.url,
        "data": meta.get("upload_date"),
        "duracao": hms(info["duration_s"]),
        "resolucao": f'{info["width"]}x{info["height"]}',
        "capitulos": chapters,
        "legendas": subs,
        "descricao": (meta.get("description") or "")[:3000],
    })


# ---------------------------------------------------------------- frames

def sample_gray(video: Path, every: float, w: int, h: int):
    import numpy as np

    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-an", "-vf",
                           f"fps=1/{every},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                          capture_output=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg falhou ao amostrar frames:\n{proc.stderr.decode(errors='replace')[-1500:]}")
    n = len(proc.stdout) // (w * h)
    return np.frombuffer(proc.stdout[: n * w * h], np.uint8).reshape(n, h, w)


def changed(a, b) -> float:
    """Fraction of pixels that changed noticeably: robust to compression noise, sensitive to new text."""
    import numpy as np

    return float((np.abs(a.astype(np.int16) - b.astype(np.int16)) > 28).mean())


def select_frames(gray, every: float, screen_thr: float, step_thr: float) -> list[dict]:
    """One 'tela' = run of samples without a big change. Within it keep the frames where the
    content grew (typing/scrolling) and always the last one, which holds the most complete code."""
    picks: list[dict] = []
    screen = 0
    start = 0
    last_kept = 0
    picks.append({"i": 0, "tela": 0, "motivo": "inicio"})
    for i in range(1, len(gray)):
        if changed(gray[i - 1], gray[i]) >= screen_thr:
            if picks[-1]["i"] != i - 1 and i - 1 > start:
                picks.append({"i": i - 1, "tela": screen, "motivo": "fim_da_tela"})
            screen += 1
            start = last_kept = i
            picks.append({"i": i, "tela": screen, "motivo": "nova_tela"})
        elif changed(gray[last_kept], gray[i]) >= step_thr:
            last_kept = i
            picks.append({"i": i, "tela": screen, "motivo": "conteudo_mudou"})
    if picks[-1]["i"] != len(gray) - 1:
        picks.append({"i": len(gray) - 1, "tela": screen, "motivo": "fim_da_tela"})
    for p in picks:
        p["t"] = round(p["i"] * every + every / 2, 2)
    return picks


def grab(video: Path, t: float, out: Path) -> bool:
    capture(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(out)])
    return out.exists()


def contact_sheets(frames: list[dict], frames_dir: Path, out_dir: Path, per_page: int) -> list[str]:
    from PIL import Image, ImageDraw

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()
    pages = []
    cols, tw = 4, 480
    for page, k in enumerate(range(0, len(frames), per_page), 1):
        chunk = frames[k:k + per_page]
        tiles = []
        for f in chunk:
            im = Image.open(frames_dir / f["arquivo"]).convert("RGB")
            im = im.resize((tw, max(1, round(im.height * tw / im.width))))
            d = ImageDraw.Draw(im)
            label = f'#{f["n"]} {f["tempo"]} tela {f["tela"]}'
            d.rectangle([0, 0, 10 + 7 * len(label), 18], fill=(0, 0, 0))
            d.text((5, 3), label, fill=(255, 255, 0))
            tiles.append(im)
        th = max(t.height for t in tiles)
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tw, rows * th), (30, 30, 30))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % cols) * tw, (i // cols) * th))
        name = f"contact_{page:02d}.png"
        sheet.save(out_dir / name)
        pages.append(str(out_dir / name))
    return pages


def cmd_frames(args) -> None:
    video = find_video(args.pasta)
    work = project_dir(args.pasta) / WORK
    frames_dir = work / "frames"
    info = probe(video)
    print(f"  amostrando a cada {args.every}s ({info['duration_s'] / 60:.1f} min)...", flush=True)
    gray = sample_gray(video, args.every, 256, 144)
    picks = select_frames(gray, args.every, args.screen, args.step)
    if len(picks) > args.max_frames:
        # keep every screen boundary, thin out the intermediate "content changed" frames
        keep = [p for p in picks if p["motivo"] != "conteudo_mudou"]
        mid = [p for p in picks if p["motivo"] == "conteudo_mudou"]
        room = max(0, args.max_frames - len(keep))
        if room and mid:
            stride = len(mid) / room
            keep += [mid[int(j * stride)] for j in range(min(room, len(mid)))]
        picks = sorted(keep, key=lambda p: p["t"])

    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    frames = []
    print(f"  extraindo {len(picks)} frames em resolução cheia...", flush=True)
    for n, p in enumerate(picks, 1):
        name = f"{n:04d}_{hms(p['t'], '-')}.png"
        if grab(video, p["t"], frames_dir / name):
            frames.append({"n": n, "arquivo": name, "t": p["t"], "tempo": hms(p["t"]),
                           "tela": p["tela"], "motivo": p["motivo"]})
    sheets = contact_sheets(frames, frames_dir, work / "contact", args.per_page)
    (work / "frames.json").write_text(json.dumps({"video": str(video), **info, "every": args.every,
                                                  "screen": args.screen, "step": args.step,
                                                  "frames": frames}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    dump({"frames": len(frames), "telas": len({f["tela"] for f in frames}),
          "pasta_frames": str(frames_dir), "contact_sheets": sheets, "indice": str(work / "frames.json")})


def cmd_frame(args) -> None:
    video = find_video(args.pasta)
    root = project_dir(args.pasta)
    out_dir = (root / args.into) if args.into else (root / WORK / "frames_extra")
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for at in args.at:
        t = parse_time(at)
        out = out_dir / f"{args.prefix}{hms(t, '-')}.png"
        if grab(video, t, out):
            saved.append(str(out))
    dump({"salvos": saved})


def cmd_crop(args) -> None:
    from PIL import Image

    x, y, w, h = (int(v) for v in args.box.split(","))
    im = Image.open(args.imagem).crop((x, y, x + w, y + h))
    if args.scale != 1:
        im = im.resize((round(w * args.scale), round(h * args.scale)), Image.LANCZOS)
    out = args.o or args.imagem.with_name(f"{args.imagem.stem}_crop_{x}_{y}.png")
    im.save(out)
    dump({"salvo": str(out), "tamanho": list(im.size)})


# ---------------------------------------------------------------- transcrever

def paragraphs(words: list[dict], gap: float, max_len: float) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    cur: list[str] = []
    t0 = prev_end = None
    for w in words:
        if t0 is not None and (w["start"] - prev_end > gap or w["start"] - t0 > max_len):
            out.append((t0, " ".join(cur)))
            cur, t0 = [], None
        if t0 is None:
            t0 = w["start"]
        cur.append(w["text"])
        prev_end = w["end"]
    if cur:
        out.append((t0, " ".join(cur)))
    return out


def vtt_words(path: Path) -> list[dict]:
    """Cues from a YouTube .vtt as pseudo-words (one per cue), dropping the rolling duplicates of auto-subs."""
    words, seen = [], set()
    block_t = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"(\d+:\d+:\d+\.\d+|\d+:\d+\.\d+) --> (\d+:\d+:\d+\.\d+|\d+:\d+\.\d+)", line)
        if m:
            block_t = (parse_time(m.group(1)), parse_time(m.group(2)))
            continue
        text = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        if not text or block_t is None or text in seen or text.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        seen.add(text)
        words.append({"text": text, "start": block_t[0], "end": block_t[1]})
    return words


def cmd_transcrever(args) -> None:
    video = find_video(args.pasta)
    root = project_dir(args.pasta)
    work = root / WORK
    if args.legenda:
        vtts = sorted((root / "video").glob("*.vtt"))
        if args.language:
            vtts = [v for v in vtts if f".{args.language}" in v.name] or vtts
        if not vtts:
            sys.exit("o vídeo não tem legendas do YouTube; use a transcrição (Groq/Whisper)")
        words = vtt_words(vtts[0])
        source = f"legenda do YouTube ({vtts[0].name})"
    else:
        from videokit.transcribe import transcribe_all
        from videokit.transcript import load_words, transcript_path

        if transcribe_all([video], work, language=args.language or None, prompt=None, engine=args.engine):
            sys.exit("transcrição falhou")
        words = load_words(transcript_path(work, video.stem), only_words=True)
        source = "transcrição de áudio (video-toolkit)"

    lines = [f"# Transcrição\n\nFonte: {source}\n"]
    lines += [f"**[{hms(t)}]** {text}\n" for t, text in paragraphs(words, args.gap, args.max_len)]
    out = root / "transcricao.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    dump({"transcricao": str(out), "trechos": len(lines) - 1, "fonte": source})


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("destino")
    p.add_argument("--set")
    p.set_defaults(fn=cmd_destino)

    p = sub.add_parser("baixar")
    p.add_argument("url")
    p.add_argument("--destino", required=True)
    p.add_argument("--nome", help="nome da pasta (padrão: título do vídeo)")
    p.add_argument("--max-height", type=int, default=1080, help="1080 deixa o código legível; 1440 para fontes muito pequenas")
    p.add_argument("--sub-langs", default="pt.*,en.*")
    p.set_defaults(fn=cmd_baixar)

    p = sub.add_parser("frames")
    p.add_argument("pasta", type=Path)
    p.add_argument("--every", type=float, default=2.0, help="segundos entre amostras")
    p.add_argument("--screen", type=float, default=0.35, help="fração de pixels mudados que conta como tela nova")
    p.add_argument("--step", type=float, default=0.03, help="mudança mínima dentro da mesma tela para guardar outro frame")
    p.add_argument("--max-frames", type=int, default=400)
    p.add_argument("--per-page", type=int, default=20)
    p.set_defaults(fn=cmd_frames)

    p = sub.add_parser("frame")
    p.add_argument("pasta", type=Path)
    p.add_argument("--at", action="append", required=True, help="hh:mm:ss, mm:ss ou segundos")
    p.add_argument("--into", help="subpasta relativa à pasta do vídeo (ex.: conferencia/src-app.py)")
    p.add_argument("--prefix", default="")
    p.set_defaults(fn=cmd_frame)

    p = sub.add_parser("crop")
    p.add_argument("imagem", type=Path)
    p.add_argument("--box", required=True, help="x,y,w,h em pixels da imagem original")
    p.add_argument("--scale", type=float, default=2.0)
    p.add_argument("-o", type=Path)
    p.set_defaults(fn=cmd_crop)

    p = sub.add_parser("transcrever")
    p.add_argument("pasta", type=Path)
    p.add_argument("--language", default=None, help="pt, en... (padrão: detectar)")
    p.add_argument("--engine", choices=("auto", "mediacript", "whisper"), default="auto")
    p.add_argument("--legenda", action="store_true", help="usar a legenda do YouTube (sem chave, instantâneo)")
    p.add_argument("--gap", type=float, default=1.2, help="pausa (s) que abre novo parágrafo")
    p.add_argument("--max-len", type=float, default=45.0, help="duração máxima (s) de um parágrafo")
    p.set_defaults(fn=cmd_transcrever)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    run_main(main)

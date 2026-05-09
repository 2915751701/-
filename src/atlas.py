import json
from pathlib import Path
from PIL import Image

ROW_SPECS = [
    ("idle", 0, 6),
    ("running-right", 1, 8),
    ("running-left", 2, 8),
    ("waving", 3, 4),
    ("jumping", 4, 5),
    ("failed", 5, 8),
    ("waiting", 6, 6),
    ("running", 7, 6),
    ("review", 8, 6),
]

DURATIONS = {
    "idle": [280, 110, 110, 140, 140, 320],
    "running-right": [120, 120, 120, 120, 120, 120, 120, 220],
    "running-left": [120, 120, 120, 120, 120, 120, 120, 220],
    "waving": [140, 140, 140, 280],
    "jumping": [140, 140, 140, 140, 280],
    "failed": [140, 140, 140, 140, 140, 140, 140, 240],
    "waiting": [150, 150, 150, 150, 150, 260],
    "running": [120, 120, 120, 120, 120, 220],
    "review": [150, 150, 150, 150, 150, 280],
}

CELL_W = 192
CELL_H = 208


def extract_frames(spritesheet_path: Path, output_dir: Path) -> dict:
    """Extract frames from a 1536x1872 spritesheet into state folders."""
    img = Image.open(spritesheet_path)
    if img.size != (1536, 1872):
        raise ValueError(f"Unexpected spritesheet size: {img.size}")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {}

    for state, row, frame_count in ROW_SPECS:
        state_dir = output_dir / state
        state_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for col in range(frame_count):
            left = col * CELL_W
            upper = row * CELL_H
            right = left + CELL_W
            lower = upper + CELL_H
            frame = img.crop((left, upper, right, lower))
            frame_path = state_dir / f"{col:03d}.png"
            frame.save(frame_path)
            frames.append(str(frame_path.relative_to(output_dir)))
        manifest[state] = {
            "frames": frames,
            "durations": DURATIONS[state],
        }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_manifest(output_dir: Path) -> dict:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    spritesheet = project_root / "assets" / "spritesheet.webp"
    frames_dir = project_root / "assets" / "frames"
    print(f"Extracting frames from {spritesheet} ...")
    manifest = extract_frames(spritesheet, frames_dir)
    for state, info in manifest.items():
        print(f"  {state}: {len(info['frames'])} frames")
    print(f"Done. Manifest written to {frames_dir / 'manifest.json'}")

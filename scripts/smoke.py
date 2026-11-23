"""Hardware smoke test: proves GameSense drives the keyboard and mouse.

    .venv\\Scripts\\python scripts\\smoke.py

Shows solid red (2 s) -> green (2 s) -> rainbow sweep (5 s), then hands lighting back to GG.
"""
import colorsys
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ckl.gamesense import BITMAP_LEN, GRID_COLS, GameSenseClient, read_address  # noqa: E402


def solid(rgb):
    return [rgb] * BITMAP_LEN


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print("GameSense address:", read_address())
    gs = GameSenseClient()
    gs.connect()
    try:
        for name, rgb in (("red", (255, 0, 0)), ("green", (0, 255, 0))):
            print("solid", name)
            t_end = time.monotonic() + 2
            while time.monotonic() < t_end:
                assert gs.send_frame(solid(rgb), [rgb] * 3), gs.last_error
                time.sleep(0.1)
        print("rainbow sweep")
        t0 = time.monotonic()
        frames = 0
        while time.monotonic() - t0 < 5:
            t = time.monotonic() - t0
            bm = []
            for i in range(BITMAP_LEN):
                col = i % GRID_COLS
                r, g, b = colorsys.hsv_to_rgb((col / GRID_COLS + t * 0.5) % 1.0, 1, 1)
                bm.append((int(r * 255), int(g * 255), int(b * 255)))
            mouse = [bm[0], bm[7], bm[14]]
            if not gs.send_frame(bm, mouse):
                print("frame failed:", gs.last_error)
            frames += 1
            time.sleep(1 / 30)
        print(f"sent {frames} frames in 5 s ({frames / 5:.1f} fps)")
    finally:
        gs.close()
        print("released lighting back to GG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

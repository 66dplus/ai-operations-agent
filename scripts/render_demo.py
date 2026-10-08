"""Edit actual Computer Use captures into a captioned, silent GitHub demo.

Capture files stay outside Git. This editor changes presentation and timing only;
all product text and states come from the recorded browser screenshots.
"""
import argparse
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS = 1920, 1080, 30
SOURCE_SIZE = (1280, 720)
SCREEN = (232, 134, 1456, 819)
INK, BLUE, MUTED = '#EDF2FF', '#6F95FF', '#A6B4CE'
FULL = (1.0, 640, 360)
INPUT = (1.22, 640, 390)
RESULTS = (1.12, 640, 330)
EVIDENCE = (1.45, 960, 300)
SOURCE = (1.45, 960, 320)
DRAFT = (1.35, 960, 395)
APPROVAL = (1.38, 960, 450)


@dataclass(frozen=True)
class Clip:
    label: str
    chapter: int
    seconds: float
    files: tuple[str, ...] = ()
    camera_from: tuple = FULL
    camera_to: tuple = FULL
    cursor_from: tuple | None = None
    cursor_to: tuple | None = None
    click: bool = False
    card: str | None = None


def storyboard(records):
    # shortcut: this edit targets one recorded scenario; a new recording must
    # keep the named stages and update preview/teaser chapter times together.
    def files(stage):
        values = tuple(item['file'] for item in records if item['stage'] == stage)
        if not values:
            raise ValueError(f'Missing recorded action: {stage}')
        return values

    def cursor(stage):
        item = next(item for item in records if item['stage'] == stage)
        return tuple(item['cursor'][axis] for axis in ('x', 'y'))

    start, company = cursor('ready'), cursor('choose-company')
    approve, export = cursor('approve-ready'), cursor('export-ready')
    return [
        Clip('From one request to reviewed companies.', 0, 3.5, card='intro'),
        Clip('Describe the companies you want to find.', 1, 2, ('000-start.jpg',), FULL, INPUT),
        Clip('One request. Your target and your offering.', 1, 5, files('typing'), INPUT, INPUT),
        Clip('Start the research.', 1, 1.5, files('ready'), INPUT, INPUT, (760, 400), start, True),
        Clip('Companies appear as the research progresses.', 2, 7, files('progress'), FULL, FULL, card='accelerated'),
        Clip('50 sample companies. 40 qualified results.', 2, 4, files('results'), FULL, RESULTS),
        Clip('Open a company to inspect its fit.', 2, 1.5, files('choose-company'), RESULTS, RESULTS, (920, 450), company, True),
        Clip('A fit score with an explanation and evidence.', 3, 5, files('company'), FULL, EVIDENCE),
        Clip('Inspect the original saved source.', 3, 1, files('source-list'), EVIDENCE, EVIDENCE),
        Clip('Inspect the original saved source.', 3, 1, files('source-expanded'), EVIDENCE, SOURCE),
        Clip('Match the quotation to the source text.', 3, 5, files('source-read'), SOURCE, SOURCE),
        Clip('Review the introduction before approving it.', 4, 2, files('draft'), DRAFT, DRAFT),
        Clip('Edit the message in your own words.', 4, 5, files('edit-typing'), DRAFT, DRAFT),
        Clip('You control the final wording.', 4, 2, files('edited'), DRAFT, APPROVAL),
        Clip('Approve this saved version.', 4, 1.5, files('approve-ready'), APPROVAL, APPROVAL, (980, 485), approve, True),
        Clip('Revision 2 approved. Nothing is sent automatically.', 4, 4, files('approved-confirmed'), APPROVAL, APPROVAL),
        Clip('Export only the results you have approved.', 5, 3, files('approved-filter'), FULL, FULL),
        Clip('Download the approved CSV.', 5, 1.5, files('export-ready'), FULL, FULL, (660, 460), export, True),
        Clip('One approved company. The exact saved draft.', 5, 3, files('exported'), FULL, FULL, card='download'),
        Clip('Saved research and approval survive a reload.', 5, 2.5, files('restored-confirmed'), FULL, FULL),
        Clip('Research. Verify. Review. Export.', 0, 3.5, card='outro'),
    ]


def smooth(value):
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def interpolate(before, after, amount):
    return tuple(a + (b - a) * amount for a, b in zip(before, after))


class Editor:
    def __init__(self, captures, font_dir):
        self.captures = captures
        self.font_dir = font_dir
        self.background = Image.new('RGB', (WIDTH, HEIGHT))
        draw = ImageDraw.Draw(self.background)
        for y in range(HEIGHT):
            ratio = y / HEIGHT
            color = tuple(round(a + (b - a) * ratio) for a, b in zip((14, 24, 44), (24, 37, 65)))
            draw.line((0, y, WIDTH, y), fill=color)

    @lru_cache(maxsize=16)
    def font(self, size, weight=400):
        path = self.font_dir / f'inter-latin-{weight}-normal.woff2'
        return ImageFont.truetype(str(path), size)

    @lru_cache(maxsize=8)
    def source(self, filename):
        image = Image.open(self.captures / 'frames' / filename).convert('RGB')
        if image.size != SOURCE_SIZE:
            raise ValueError(f'{filename}: expected capture size {SOURCE_SIZE}, got {image.size}')
        return image

    def chrome(self, canvas, chapter, progress):
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle((232, 44, 278, 90), radius=11, fill='#335AE5')
        draw.text((242, 54), 'ao', font=self.font(21, 700), fill='white')
        draw.text((294, 51), 'AI Operations Agent', font=self.font(28, 600), fill=INK)
        draw.rounded_rectangle((1284, 46, 1688, 88), radius=21, fill='#273755')
        draw.ellipse((1303, 62, 1314, 73), fill='#85A7FF')
        draw.text((1325, 58), 'OFFLINE DEMO · SAMPLE DATA', font=self.font(17, 600), fill=INK)
        if chapter:
            for index in range(1, 6):
                x = 1688 - (6 - index) * 34
                draw.rounded_rectangle((x, 1014, x + 22, 1020), radius=3, fill=BLUE if index <= chapter else '#40506D')
        draw.line((232, 1060, 1688, 1060), fill='#364563', width=2)
        draw.line((232, 1060, 232 + round(1456 * progress), 1060), fill=BLUE, width=3)

    def pointer(self, canvas, position, crop, phase, click):
        left, top, right, bottom = crop
        sx, sy, width, height = SCREEN
        x = sx + (position[0] - left) / (right - left) * width
        y = sy + (position[1] - top) / (bottom - top) * height
        draw = ImageDraw.Draw(canvas)
        if click and phase > .70:
            radius = 12 + (phase - .70) * 95
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=BLUE, width=3)
        points = [(x, y), (x + 1, y + 31), (x + 9, y + 24), (x + 15, y + 37), (x + 22, y + 34), (x + 16, y + 22), (x + 28, y + 21)]
        draw.polygon(points, fill='white', outline='#183252', width=2)

    def card(self, canvas, kind, phase):
        draw = ImageDraw.Draw(canvas)
        if kind == 'download':
            draw.rounded_rectangle((995, 773, 1648, 915), radius=20, fill='#18334F', outline='#547CAF', width=2)
            draw.rounded_rectangle((1023, 805, 1087, 869), radius=12, fill='#2B5879')
            draw.text((1032, 827), 'CSV', font=self.font(18, 700), fill='white')
            draw.text((1110, 800), 'approved-companies.csv', font=self.font(25, 600), fill='white')
            draw.text((1110, 848), 'Downloaded · 1 company · Revision 2', font=self.font(20), fill='#C2D4EA')
            return
        canvas.paste(self.background, (0, 0))
        draw = ImageDraw.Draw(canvas)
        shift = round(24 * (1 - smooth(min(1, phase * 5))))
        draw.text((232, 187 + shift), 'AI OPERATIONS AGENT', font=self.font(23, 600), fill=BLUE)
        title = ['One request.', 'Companies ready for review.'] if kind == 'intro' else ['Research. Verify.', 'Keep the final say.']
        for index, line in enumerate(title):
            draw.text((232, 265 + index * 110 + shift), line, font=self.font(74, 700), fill='white')
        subtitle = 'Website evidence, fit scores and editable introductions.' if kind == 'intro' else 'Human approval first. Export the exact saved version.'
        draw.text((235, 524 + shift), subtitle, font=self.font(31), fill='#BDCCE5')
        badges = ['Verified quotations', 'Fit scores', 'Human review', 'CSV / JSON']
        x = 232
        for text in badges:
            width = round(draw.textlength(text, font=self.font(23, 600))) + 42
            draw.rounded_rectangle((x, 651, x + width, 706), radius=13, fill='#253753', outline='#3A5277')
            draw.text((x + 21, 666), text, font=self.font(23, 600), fill='#D7E3F7')
            x += width + 16
        draw.text((235, 810), 'Recorded through the actual local UI with a synthetic sample dataset.', font=self.font(25), fill=MUTED)

    def frame(self, clip, local_frame, global_progress):
        canvas = self.background.copy()
        frames = max(1, round(clip.seconds * FPS))
        phase = local_frame / max(1, frames - 1)
        if clip.card in ('intro', 'outro'):
            self.card(canvas, clip.card, phase)
        else:
            border = ImageDraw.Draw(canvas)
            border.rounded_rectangle((215, 112, 1705, 974), radius=24, fill='#0A1224')
            border.rounded_rectangle((228, 120, 1692, 958), radius=16, fill='#F7F9FC')
            index = min(len(clip.files) - 1, int(phase * len(clip.files)))
            source = self.source(clip.files[index])
            zoom, center_x, center_y = interpolate(clip.camera_from, clip.camera_to, smooth(min(1, local_frame / (FPS * 1.4))))
            width, height = SOURCE_SIZE[0] / zoom, SOURCE_SIZE[1] / zoom
            left = max(0, min(SOURCE_SIZE[0] - width, center_x - width / 2))
            top = max(0, min(SOURCE_SIZE[1] - height, center_y - height / 2))
            crop = (left, top, left + width, top + height)
            screen = source.resize(SCREEN[2:], Image.Resampling.LANCZOS, box=crop)
            canvas.paste(screen, SCREEN[:2])
            if clip.cursor_to:
                position = interpolate(clip.cursor_from, clip.cursor_to, smooth(min(1, phase / .72)))
                self.pointer(canvas, position, crop, phase, clip.click)
            if clip.card == 'download':
                self.card(canvas, 'download', phase)
        self.chrome(canvas, clip.chapter, global_progress)
        draw = ImageDraw.Draw(canvas)
        if clip.card not in ('intro', 'outro'):
            draw.text((232, 1000), f'{clip.chapter:02}', font=self.font(28, 600), fill=BLUE)
            draw.text((295, 997), clip.label, font=self.font(28, 600), fill=INK)
            if clip.card == 'accelerated':
                draw.rounded_rectangle((1232, 907, 1658, 941), radius=10, fill='#22344E')
                draw.text((1251, 916), 'Processing footage accelerated', font=self.font(17), fill='white')
        return canvas


def render(editor, clips, output):
    total_frames = sum(round(clip.seconds * FPS) for clip in clips)
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise SystemExit('ffmpeg is required to render the demo.')
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', f'{WIDTH}x{HEIGHT}', '-r', str(FPS), '-i', 'pipe:0', '-an', '-c:v', 'libx264',
               '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    frame_index = 0
    previous_end = None
    try:
        for clip in clips:
            print(f'Rendering {clip.label}', flush=True)
            for local_frame in range(round(clip.seconds * FPS)):
                frame = editor.frame(clip, local_frame, frame_index / max(1, total_frames - 1))
                if previous_end is not None and local_frame < 6:
                    frame = Image.blend(previous_end, frame, smooth((local_frame + 1) / 6))
                process.stdin.write(frame.tobytes())
                frame_index += 1
            previous_end = frame
        process.stdin.close()
        if process.wait() != 0:
            raise SystemExit('ffmpeg failed; inspect the encoder diagnostic.')
    except BaseException:
        if process.poll() is None:
            process.terminate()
            process.wait()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', type=Path, required=True, help='Folder containing capture.json and frames/')
    parser.add_argument('--output', type=Path, required=True, help='Final MP4 path')
    parser.add_argument('--stills', type=Path, help='Render chapter previews instead of a video')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    records = json.loads((args.captures / 'capture.json').read_text())
    clips = storyboard(records)
    editor = Editor(args.captures, root / 'frontend/node_modules/@fontsource/inter/files')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.stills:
        args.stills.mkdir(parents=True, exist_ok=True)
        for index in (0, 2, 5, 7, 10, 12, 15, 18, 20):
            clip = clips[index]
            editor.frame(clip, round(clip.seconds * FPS / 2), .5).save(args.stills / f'{index:02}.jpg', quality=95)
    else:
        render(editor, clips, args.output)
    print(json.dumps({'duration_seconds': sum(clip.seconds for clip in clips), 'fps': FPS, 'resolution': [WIDTH, HEIGHT]}))


if __name__ == '__main__':
    main()

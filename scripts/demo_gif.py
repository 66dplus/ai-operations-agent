"""Create a small README teaser from the recorded and edited MP4."""
from pathlib import Path
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    video = root / 'docs/verification/demo.mp4'
    if not video.exists():
        raise SystemExit('Render docs/verification/demo.mp4 first.')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise SystemExit('ffmpeg is required to create the README teaser.')
    # Short excerpts preserve actual typing, results, source inspection and approval.
    sections = [(5.5, 8.5), (20.0, 23.0), (29.5, 32.5), (46.0, 49.0)]
    filters = [f'[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[s{i}]'
               for i, (start, end) in enumerate(sections)]
    inputs = ''.join(f'[s{i}]' for i in range(len(sections)))
    filters.append(inputs + f'concat=n={len(sections)}:v=1:a=0,fps=10,scale=960:-1:flags=lanczos,split[a][b]')
    filters.extend(['[a]palettegen=stats_mode=diff[p]', '[b][p]paletteuse=dither=bayer:bayer_scale=4'])
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(video),
                    '-filter_complex', ';'.join(filters), '-loop', '0', str(video.with_suffix('.gif'))], check=True)
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', '26.5', '-i', str(video),
                    '-frames:v', '1', '-update', '1', '-q:v', '2', str(video.with_name('demo-poster.jpg'))], check=True)
    print('Created a 12-second README GIF and a poster from the actual demo video.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# 描述: 视频无字幕时的 whisper 语音转写兜底（依赖 models/ 大模型）
"""对 qfps_remaining.json 中的 B 站视频做 ASR 转写(yt-dlp 下音频 -> ffmpeg 转 16k wav -> whisper.cpp)。
输出追加到 qfps_asr_text.txt,格式与 qfps_videos_text.txt 一致;支持断点续跑(跳过已转写 bvid)。

用法:
  python3 asr_transcribe.py            # 跑全部 remaining
  python3 asr_transcribe.py --limit 1  # 只跑 1 个(测试)
  python3 asr_transcribe.py --bvid BVxxxx  # 只跑指定 bvid
"""
import sys, json, re, shutil, subprocess, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMAIN = HERE / "qfps_remaining.json"
OUT = HERE / "qfps_asr_text.txt"
MODEL = HERE / "models" / "ggml-large-v3-turbo.bin"
COOKIE = (HERE / "cookie.txt").read_text(encoding="utf-8").strip()

def find_bin(*names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None

YTDLP = find_bin("yt-dlp")
FFMPEG = find_bin("ffmpeg")
WHISPER = find_bin("whisper-cli", "whisper-cpp", "main")

def done_bvids():
    if not OUT.exists():
        return set()
    txt = OUT.read_text(encoding="utf-8")
    return set(re.findall(r"\(([A-Za-z0-9]+)\)\s*=====", txt))

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)

def transcribe_one(v, idx, tmp):
    bvid = v["bvid"]
    url = f"https://www.bilibili.com/video/{bvid}"
    audio = tmp / f"{bvid}.m4a"
    # 1) 下音频
    r = run([YTDLP, "-f", "bestaudio", "--no-playlist", "--add-header",
             f"Cookie:{COOKIE}", "-o", str(tmp / f"{bvid}.%(ext)s"), url])
    got = list(tmp.glob(f"{bvid}.*"))
    got = [g for g in got if g.suffix != ".wav"]
    if not got:
        return None, f"下载失败: {r.stderr.strip()[-200:]}"
    src = got[0]
    # 2) 转 16k mono wav
    wav = tmp / f"{bvid}.wav"
    r = run([FFMPEG, "-y", "-i", str(src), "-ar", "16000", "-ac", "1",
             "-c:a", "pcm_s16le", str(wav)])
    if not wav.exists():
        return None, f"ffmpeg失败: {r.stderr.strip()[-200:]}"
    # 3) whisper 转写
    of = tmp / bvid
    r = run([WHISPER, "-m", str(MODEL), "-l", "zh", "-nt", "-f", str(wav),
             "-otxt", "-of", str(of)])
    txtf = tmp / f"{bvid}.txt"
    if not txtf.exists():
        return None, f"whisper失败: {r.stderr.strip()[-200:]}"
    text = re.sub(r"\s+", "", txtf.read_text(encoding="utf-8"))
    return text, f"ok len={len(text)}"

def main():
    args = sys.argv[1:]
    limit = None; only = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    if "--bvid" in args:
        only = args[args.index("--bvid") + 1]
    for name, b in [("yt-dlp", YTDLP), ("ffmpeg", FFMPEG), ("whisper", WHISPER)]:
        if not b:
            sys.exit(f"缺少 {name}")
    if not MODEL.exists():
        sys.exit(f"缺少模型 {MODEL}")

    rem = json.load(open(REMAIN))
    done = done_bvids()
    todo = [v for v in rem if v["bvid"] not in done]
    if only:
        todo = [v for v in rem if v["bvid"] == only]
    if limit:
        todo = todo[:limit]
    print(f"待转写 {len(todo)} 个(已完成 {len(done)},总 {len(rem)})")

    base_n = len(done)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for i, v in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] {v['bvid']} {v['title'][:30]} ...", flush=True)
            try:
                text, why = transcribe_one(v, base_n + i, tmp)
            except Exception as e:
                text, why = None, f"异常 {e}"
            print(f"    {why}", flush=True)
            if text:
                with open(OUT, "a", encoding="utf-8") as f:
                    f.write(f"===== {base_n + i}. [{v['time']}] {v['title']} ({v['bvid']}) =====\n")
                    f.write(text + "\n\n")
            for g in tmp.glob(f"{v['bvid']}.*"):
                g.unlink(missing_ok=True)
    print("完成")

if __name__ == "__main__":
    main()

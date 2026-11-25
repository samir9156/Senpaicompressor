import os, re, json, time, asyncio, tempfile, shutil
from pyrogram import Client, filters

app = Client("bot", api_id=int(os.environ["API_ID"]), api_hash=os.environ["API_HASH"],
             bot_token=os.environ["BOT_TOKEN"], workdir="/tmp")
sem = asyncio.Semaphore(1)  # ek time pe ek hi job
PIPE, DEVNULL = asyncio.subprocess.PIPE, asyncio.subprocess.DEVNULL

HELP = ("Video bhejo, fir us video pe reply karo:\n\n"
        "res same crf same codec h265\n"
        "res 720 crf 20 codec h264\n"
        "res 1280x720 codec hevc\n"
        "h265\n\n"
        "Jo na likho: res same, crf same, codec h264.\n"
        "Caption mein bhi command likh sakte ho.")


def bar(pct, n=12):
    f = int(n * pct / 100)
    return "█" * f + "░" * (n - f)


class Prog:
    def __init__(self, msg, title):
        self.msg, self.title, self.last = msg, title, 0

    async def update(self, pct, extra="", force=False):
        now = time.time()
        if not force and now - self.last < 3:  # telegram flood se bachne ke liye
            return
        self.last = now
        try:
            await self.msg.edit(f"{self.title}\n{bar(pct)} {pct:.0f}%{extra}")
        except Exception:
            pass

    def cb(self):
        async def f(cur, tot):
            if tot:
                await self.update(cur * 100 / tot, f"  {cur/1e6:.1f}/{tot/1e6:.1f} MB")
        return f


def parse(t):
    t = t.lower()
    codec = "libx265" if re.search(r"h\.?265|hevc|x265", t) else "libx264"
    r = re.search(r"res\w*\s*[:=]?\s*(same|\d{3,4}x\d{3,4}|\d{3,4})", t)
    res = None
    if r and r.group(1) != "same":
        v = r.group(1)
        res = v.replace("x", ":") if "x" in v else f"-2:{v}"
    c = re.search(r"crf\s*[:=]?\s*(same|\d{1,2})", t)
    crf = None if (not c or c.group(1) == "same") else int(c.group(1))
    return codec, res, crf


def src_crf(path):
    try:
        with open(path, "rb") as f:
            m = re.search(rb"crf=(\d+(?:\.\d+)?)", f.read(1_000_000))
        return round(float(m.group(1))) if m else None
    except Exception:
        return None


async def probe(path):
    p = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration", "-of", "json",
        path, stdout=PIPE, stderr=DEVNULL)
    out, _ = await p.communicate()
    try:
        j = json.loads(out)
        s = j["streams"][0]
        return float(j["format"]["duration"]), s["width"], s["height"]
    except Exception:
        return 0, 0, 0


async def work(cmd_msg, vid_msg, text):
    if not (vid_msg.video or vid_msg.document):
        return
    codec, res, crf = parse(text)
    st = await cmd_msg.reply("Starting...", quote=True)
    async with sem:
        d = tempfile.mkdtemp()
        try:
            # 1) download
            pr = Prog(st, "⬇️ Download")
            inp = await vid_msg.download(file_name=d + "/in.mp4", progress=pr.cb())
            await pr.update(100, force=True)
            if crf is None:
                crf = src_crf(inp) or 20  # source ka crf mila to wahi, warna 20
            dur, _, _ = await probe(inp)

            # 2) encode
            out = d + "/out.mp4"
            cmd = ["ffmpeg", "-y", "-i", inp]
            if res:
                cmd += ["-vf", f"scale={res}:flags=lanczos"]
            cmd += ["-c:v", codec, "-crf", str(crf), "-preset", "fast", "-c:a", "copy",
                    "-movflags", "+faststart"]
            if codec == "libx265":
                cmd += ["-tag:v", "hvc1"]
            cmd += ["-progress", "pipe:1", "-nostats", out]
            label = f"⚙️ Encode {codec[3:]} crf {crf} res {res or 'same'}"
            pr = Prog(st, label)
            p = await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, stderr=DEVNULL)
            speed = ""
            async for raw in p.stdout:
                line = raw.decode(errors="ignore").strip()
                if line.startswith("out_time_us="):
                    try:
                        t = int(line.split("=")[1]) / 1e6
                    except ValueError:
                        continue
                    if dur:
                        await pr.update(min(t * 100 / dur, 99), f"  {speed}")
                elif line.startswith("speed="):
                    speed = line.split("=")[1]
            if await p.wait() != 0:
                return await st.edit("❌ Encode fail")
            await pr.update(100, force=True)

            # 3) upload
            d2, w, h = await probe(out)
            pr = Prog(st, "⬆️ Upload")
            cap = (f"{codec[3:]} crf {crf} | {h}p | "
                   f"{os.path.getsize(inp)/1e6:.1f} → {os.path.getsize(out)/1e6:.1f} MB")
            await vid_msg.reply_video(out, caption=cap, duration=int(d2), width=w, height=h,
                                      supports_streaming=True, quote=True, progress=pr.cb())
            await st.delete()
        except Exception as e:
            await st.edit(f"❌ Error: {str(e)[:200]}")
        finally:
            shutil.rmtree(d, ignore_errors=True)


@app.on_message(filters.command(["start", "help"]))
async def start(c, m):
    await m.reply(HELP)


@app.on_message(filters.text & filters.reply & ~filters.command(["start", "help"]))
async def on_reply(c, m):
    await work(m, m.reply_to_message, m.text)


@app.on_message((filters.video | filters.document) & filters.caption)
async def on_caption(c, m):
    await work(m, m, m.caption)


app.run()

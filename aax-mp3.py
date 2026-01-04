import asyncio
import logging
import typing as ty
import json
import re
from pathlib import Path
from dataclasses import dataclass
import platform

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
import click

DEFAULT_PATH = "/usr/bin" if platform.system() == "Linux" else r"c:\Program Files\fmpeg\bin"

@dataclass
class Options:
    input: str
    out_path: str
    base_out_name: str
    title: str
    tool: str = DEFAULT_PATH

class Ffmpeg:
    ff_path: str
    activate_bytes: str

    def __init__(self, ff_path: str = None, activate_bytes: str = None):
        if ff_path is None:
            ff_path = r"c:\Program Files\fmpeg\bin"
        self.ff_path = ff_path
        if activate_bytes is None:
            activate_bytes = "11bb9604"
        self.activate_bytes = activate_bytes

    async def run_program(self, program:str, arguments:ty.List[str]) -> ty.Tuple[int, ty.List[str], ty.List[str]]:
        async def pump_bytes(stream: asyncio.StreamReader, prefix: str, results: ty.List[str]) -> None:
            while True:
                line = await stream.read(1024*1024)
                if not line:
                    break
                text = line.decode(errors="replace")
                results.append( text)
        process = await asyncio.create_subprocess_exec(
            program,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        outputs:ty.List[str] = []
        errors: ty.List[str] = []
        await asyncio.gather(
            pump_bytes(process.stdout, "STDOUT: ", outputs),
            pump_bytes(process.stderr, "STDERR: ", errors),
        )
        res = await process.wait()
        return res, outputs, errors

    async def get_metainfo(self, inp:str) -> ty.List[str]:
        process_program = self.ff_path + "/" + "ffprobe"
        process_opt = [  "-v", "error",
                        "-show_entries", "format_tags",
                        "-of", "json",
                        inp]
        res, outputs, errors = await self.run_program(process_program, process_opt)

        decoder = json.JSONDecoder()
        res = decoder.decode("".join(outputs))
        return res

    async def get_chapters(self, inp: str) -> ty.List:
        process_program = self.ff_path + "/" + "ffprobe"
        process_opt = [  "-v", "error",
                        "-print_format", "json",
                        "-show_chapters",
                        inp]
        res, outputs, errors = await self.run_program(process_program, process_opt)

        decoder = json.JSONDecoder()
        res = decoder.decode("".join(outputs))
        return res["chapters"]

    async def convert_aax_ap3(self, inp: str, out: str) -> None:
        process_program = self.ff_path + "/" + "ffmpeg"
        process_opt = [ "-hide_banner",
                        "-y",
                        "-activation_bytes", self.activate_bytes,
                        "-i", inp,
                        "-codec:a", "libmp3lame",
                       "-vn",
                        out]
        logger.info(f"process {process_program} {' '.join(process_opt)}")
        await self.run_program(process_program, process_opt)

    async def split_ap3(self, inp: str, out: str, start:float, dur:float, title:str) -> None:
        process_program = self.ff_path + "/" + "ffmpeg"
#        "-hide_banner", "-loglevel", "error", "-y",
#        "-i", str(inp),
#        "-ss", f"{start:.6f}",
#        "-t", f"{dur:.6f}",
#        "-map", "0:a:0",
#        "-c", "copy",
#        str(out_path),

        process_opt = [ "-hide_banner",
                        "-loglevel", "error",
                        "-y",
                        "-i", inp,
                        "-ss", f"{start:.6f}",
                        "-t", f"{dur:.6f}",
                        "-map", "0:a:0",
                        "-c", "copy",
                        "-metadata", f'title="{title}"',
                        str(out)]
        logger.info(f"process {process_program} {' '.join(process_opt)}")
        await self.run_program(process_program, process_opt)



# "c:\Program Files\fmpeg\bin\ffmpeg.exe" -y  -activation_bytes 11bb9604 -i .\DieMachtdesPrsidenten_ep7.aax  -codec:a libmp3lame .\test.mp3
#  "c:\Program Files\fmpeg\bin\ffmpeg.exe" -i test.mp3 -af silencedetect=d=0.5 -f null


def safe_name(name: str, fallback: str) -> str:
    name = name.strip() or fallback
    name = re.sub(r'[<>:"/\\|?*]+', "_", name)   # Windows-illegal chars
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180]  # keep it reasonable

async def convert(options: Options) -> None:
    out = Path(options.out_path)
    # create path if needed
    out.mkdir(parents=True, exist_ok=True)
    temp_name = "test.mp3"
    ffmpeg = Ffmpeg(activate_bytes="11bb9604", ff_path=options.tool)
    meta = await ffmpeg.get_metainfo(options.input)
    logger.debug(f"meta data: {meta}")
    await ffmpeg.convert_aax_ap3(options.input, temp_name)
    chapters = await ffmpeg.get_chapters(temp_name)
    logger.debug(f"chapters: {chapters}")
    title = options.title
    for i, ch in enumerate(chapters, start=1):
        start = float(ch["start_time"])
        end = float(ch["end_time"])
        dur = max(0.0, end - start)
        file_title = f"{i:03d} - {safe_name(title, f'{i:03d} {title}')}"
        filename = f"{file_title}.mp3"
        out_path = out / filename
        await ffmpeg.split_ap3(inp=temp_name, out=str(out_path), start=start, dur=dur, title=file_title)


async def async_main(options: Options) -> None:
    await convert(options)

@click.command()
@click.option("-i", "--input", required=True, type=str)
@click.option("-d", "--directory", help="output folder", default=".", type=str)
@click.option("-o", "--output", help="output base name", default="out", type=str)
@click.option("-t", "--title", help="adapted title")
@click.option( "--tool", help="path to ffmpeg tool", default=DEFAULT_PATH, type=str)
def main(input: str, directory: str, output: str, title, tool) -> None:
    if title is None:
        title = output
    options = Options(input=input, out_path=directory, title=title, base_out_name=output, tool=tool)
    asyncio.run(async_main(options))

if __name__ == "__main__":
    main()
import json
import subprocess
import sys

import aiofiles
import click
import httpx


def generate_diagram_code_in_child_process(view: str) -> tuple[dict, list[str]]:
    def run_child_process():
        # Run a separate Python script as a child process
        output = subprocess.check_output([sys.executable, "-m", "pystructurizr.generator", "dump", "--view", view])
        return output.decode().strip()

    # Run the child process and capture its output
    child_output = run_child_process()
    result = json.loads(child_output)
    return result['code'], result['imported_modules']


async def generate_svg(diagram_code: dict, tmp_folder: str) -> str:
    url = "https://kroki.io/structurizr/svg"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=diagram_code)

    if resp.status_code != 200:
        print(resp)
        if resp.content:
            print(resp.content.decode())
        raise click.ClickException("Failed to create diagram")

    svg_file_path = f"{tmp_folder}/diagram.svg"
    async with aiofiles.open(svg_file_path, "w") as svg_file:
        await svg_file.write(resp.text)

    return svg_file_path

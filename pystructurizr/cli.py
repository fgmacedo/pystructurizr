import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

from .cli_helper import (generate_diagram_code_in_child_process, generate_svg)
from .cli_watcher import observe_modules
from .cloudstorage import CloudStorage, create_cloud_storage


@click.command()
@click.option('--view', prompt='Your view file (e.g. examples.single_file_example)',
              help='The view file to generate.')
@click.option('--as-json', is_flag=True, default=False,
              help='Dumps the generated code and the imported modules as a json object')
def dump(view, as_json):
    diagram_code, imported_modules = generate_diagram_code_in_child_process(view)
    if as_json:
        click.echo(json.dumps({
            "code": diagram_code,
            "imported_modules": list(imported_modules)
        }))
    else:
        click.echo(diagram_code)


@click.command()
@click.option('--view', prompt='Your view file (e.g. examples.single_file_example)',
              help='The view file to develop.')
def dev(view):
    click.echo(f"Setting up live preview of view {view}...")
    with tempfile.TemporaryDirectory() as tmp_folder:
        current_script_path = Path(__file__).absolute()
        index_html = current_script_path.parent / 'index.html'
        shutil.copy(index_html, f"{tmp_folder}/index.html")

        async def async_behavior():
            click.echo("Generating diagram...")
            diagram_code, imported_modules = generate_diagram_code_in_child_process(view)
            await generate_svg(diagram_code, tmp_folder)
            return imported_modules

        async def observe_loop():
            modules_to_watch = await async_behavior()
            click.echo("Launching webserver...")
            # pylint: disable=consider-using-with
            subprocess.Popen(f"httpwatcher --root {tmp_folder} --watch {tmp_folder}", shell=True)
            await observe_modules(modules_to_watch, async_behavior)

        asyncio.run(observe_loop())


@click.group(chain=True, invoke_without_command=True)
@click.argument('view')
@click.argument('file-path', type=click.Path(exists=False))
@click.pass_context
def build(ctx, view, file_path):
    """Build VIEW into an SVG and save it to FILE_PATH.

    FILE_PATH can be a directory or a file name. If it is a directory, the file name will be the view name.

    Can be chained with `upload` to upload the resulting file to a cloud storage provider.
    """
    with tempfile.TemporaryDirectory() as tmp_folder:
        async def async_behavior():
            # Generate diagram
            diagram_code, _ = generate_diagram_code_in_child_process(view)

            # Generate SVG
            temp_svg_file_path = await generate_svg(diagram_code, tmp_folder)

            svg_file_path = Path(file_path)

            # if we only have a directory name, output should include the view name
            if svg_file_path.is_file():
                base_dir = svg_file_path.parent
            else:
                base_dir = svg_file_path
                diagram_name = view.replace(".", "_")
                svg_file_path = svg_file_path / f"{diagram_name}.svg"

            # Ensure that the directory exists
            base_dir.mkdir(parents=True, exist_ok=True)

            # Move it to the requested file name
            shutil.move(temp_svg_file_path, svg_file_path)

            ctx.ensure_object(dict)
            ctx.obj['svg_file_path'] = svg_file_path
            click.echo(svg_file_path)

        asyncio.run(async_behavior())


@build.command()
@click.option('--gcs-credentials', prompt='Path to json file containing Google Cloud Storage credentials', type=click.Path(exists=True),
              help='Path to the credentials.json file for Google Cloud Storage.')
@click.option('--bucket-name', prompt='Name of the bucket on Google Cloud Storage',
              help='The name of the bucket to use on Google Cloud Storage.')
@click.option('--object-name', prompt='Name of the object on Google Cloud Storage',
              help='The name of the object to use on Google Cloud Storage.')
@click.pass_context
def upload(ctx, gcs_credentials, bucket_name, object_name):
    async def async_behavior():
        svg_file_path = ctx.obj['svg_file_path']
        click.echo(f"Uploading {svg_file_path}")

        # Upload it to the requested cloud storage provider
        cloud_storage = create_cloud_storage(CloudStorage.Provider.GCS, gcs_credentials)
        svg_file_url = cloud_storage.upload_file(svg_file_path, bucket_name, object_name)
        click.echo(svg_file_url)

    asyncio.run(async_behavior())


@click.group()
def cli():
    pass


cli.add_command(dump)
cli.add_command(dev)
cli.add_command(build)

if __name__ == '__main__':
    cli()

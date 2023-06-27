import json
from pathlib import Path
from typing import List, Tuple

import click

from ape import project
from ape.cli import ape_cli_context


def dependency_options():
    def fn(f):
        for dependency_type in project.dependency_manager.dependency_types:
            f = click.option(f"--{dependency_type}")(f)

        return f

    return fn


@click.group()
def cli():
    """
    Manage dependencies
    """


@cli.command("list")
@click.option(
    "_all", "--all", is_flag=True, help="Include packages not referenced by local project"
)
def _list(_all):
    """
    List installed packages
    """

    output_parts: List[str] = []

    if _all:
        location = project.dependency_manager.DATA_FOLDER / "packages"
        if location.is_dir():
            dependencies = [x for x in location.iterdir()]
            for dependency in dependencies:
                output_str = click.style(dependency.name, bold=True)
                for version_dir in dependency.iterdir():
                    v_output_str = f"{output_str} {version_dir.name}"

                    file = next(version_dir.iterdir(), None)
                    if file:
                        data = json.loads(file.read_text())
                        compiled = bool(data.get("contractTypes"))
                        if compiled:
                            compiled_str = click.style("compiled!", fg="green")
                            v_output_str = f"{v_output_str}, {compiled_str}"

                        output_parts.append(v_output_str)

    else:
        # Limit to local project.
        for name, versions in project.dependencies.items():
            output_str = click.style(name, bold=True)
            for version, dep in versions.items():
                v_output_str = f"{output_str} {version}"
                compiled = bool(dep.contract_types)
                if compiled:
                    compiled_str = click.style("compiled!", fg="green")
                    v_output_str = f"{v_output_str}, {compiled_str}"

                output_parts.append(v_output_str)

    if output_parts:
        click.echo("Packages:")
        for part in output_parts:
            click.echo(f"  {part}")

    else:
        click.echo("No packages installed for this project.")


def _dependency_callback(ctx, param, value):
    try:
        path = Path(value).absolute()
    except Exception:
        path = None

    if path is not None and path.is_dir():
        return path

    elif path is not None and path.is_file() and path.name == "ape-config.yaml":
        # Allow if user put full path to config file.
        return path.parent

    elif "=" not in value:
        raise click.BadArgumentUsage(
            "'dependency' must be a path to an ape project or a value like 'name=version'."
        )

    # It is a specify dependency
    parts = value.split("=")
    name = parts[0].strip()
    version = parts[1].strip()
    return {"name": name, "version": version}


@cli.command()
@ape_cli_context()
@click.argument("dependency", callback=_dependency_callback)
@click.option("--force", "-f", help="Force a re-install", is_flag=True)
@dependency_options()
def install(cli_ctx, dependency, force, **type_kwargs):
    """
    Download and cache packages
    """

    if isinstance(dependency, Path):
        # Is a path to a project (use config).
        if dependency.absolute() == project.path.absolute():
            project.load_dependencies(use_cache=not force)
        else:
            # Change projects.
            with cli_ctx.config_manager.using_project(dependency) as _project:
                _project.load_dependencies(use_cache=not force)

        log_name = dependency.as_posix()

    else:
        # Is a specific dependency.
        data = {**dependency, **{k: v for k, v in type_kwargs.items() if v is not None}}
        dependency_obj = cli_ctx.dependency_manager.decode_dependency(data)
        dependency_obj.extract_manifest(use_cache=not force)
        log_name = f"{dependency_obj.name}={dependency_obj.version}"

    cli_ctx.logger.success(f"Package '{log_name}' installed.")


@cli.command()
@ape_cli_context()
@click.argument("name")
@click.option("--version", help="The dependency version")
@click.option("--force", "-f", help="Force a re-compile", is_flag=True)
def compile(cli_ctx, name, version, force):
    """
    Compile a package
    """

    if name not in project.dependencies:
        cli_ctx.abort(f"Dependency '{name}' unknown. Is it installed?")

    versions = project.dependencies[name]
    if not versions:
        # This shouldn't happen.
        cli_ctx.abort("No versions.")

    if not version and len(versions) == 1:
        # Version is not specified but we can use the only existing version.
        version = list(versions.keys())[0]

    elif not version:
        cli_ctx.abort("Please specify --version.")

    version_opts: Tuple
    if version == "local":
        version_opts = (version,)
    elif version.startswith("v"):
        version_opts = (f"v{version}", str(version))
    else:
        version_opts = (str(version), str(version[1:]))

    version_found = None
    for version_i in version_opts:
        if version_i in versions:
            version_found = version_i
            break

    if not version_found:
        # Return only needed for mypy
        return cli_ctx.abort(
            f"Version '{version}' for dependency '{name}' not found. Is it installed?"
        )

    dependency = versions[version_found]
    dependency.compile(use_cache=not force)

    log_line = name
    if version_found and version_found != "local":
        log_line = f"{log_line}={version_found}"

    cli_ctx.logger.success(f"Package '{log_line}' compiled.")

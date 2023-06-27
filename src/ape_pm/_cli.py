import json
from pathlib import Path
from typing import List, Tuple

import click

from ape.cli import ape_cli_context


@click.group()
def cli():
    """
    Package management tools
    """


@cli.command("list")
@ape_cli_context()
@click.option(
    "_all", "--all", is_flag=True, help="Include packages not referenced by the local project"
)
def _list(cli_ctx, _all):
    """
    List installed packages
    """

    output_parts: List[str] = []

    if _all:
        location = cli_ctx.dependency_manager.DATA_FOLDER / "packages"
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
        for name, versions in cli_ctx.project_manager.dependencies.items():
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
        message = "No packages installed"
        if not _all:
            message = f"{message} for this project"

        click.echo(f"{message}.")


def _package_callback(ctx, param, value):
    if value is None:
        # Install all packages from local project.
        return None

    elif value.startswith("gh:"):
        # Is a GitHub style dependency
        return {"github": value[3:]}

    elif value.startswith("npm:"):
        # Is an NPM style dependency
        return {"npm:": value[4:]}

    # Check if is a local package.
    try:
        path = Path(value).absolute()
    except Exception:
        path = None

    if path is not None and path.exists():
        # Is a local package somewhere.
        if path.is_file() and path.name == "ape-config.yaml":
            path = path.parent

        return {"local": path.as_posix()}

    elif ":" in value:
        # Catch-all for unknown dependency types that may exist.
        parts = value.split(":")
        return {parts[0]: parts[1]}

    raise click.BadArgumentUsage(f"Unknown package '{value}'.")


@cli.command()
@ape_cli_context()
@click.argument("package", nargs=1, required=False, callback=_package_callback)
@click.option("--name", help="The name of the dependency", metavar="NAME")
@click.option("--version", help="The dependency's version", metavar="VERSION")
@click.option(
    "--ref",
    help="A reference flag, used for GitHub branches or tags in place of version",
    metavar="REF",
)
@click.option("--force", "-f", help="Force a re-install", is_flag=True)
def install(cli_ctx, package, name, version, ref, force):
    """
    Download and cache packages
    """

    log_name = None
    if not package:
        # `ape pm install`: Load all dependencies from current package.
        cli_ctx.project_manager.load_dependencies(use_cache=not force)

    elif name:
        # `ape pm install <package>`: Is a specific package.
        data = {"name": name, **package}
        if version is not None:
            data["version"] = version
        if ref is not None:
            data["ref"] = ref

        dependency_obj = cli_ctx.dependency_manager.decode_dependency(data)
        dependency_obj.extract_manifest(use_cache=not force)
        log_name = f"{dependency_obj.name}@{dependency_obj.version_id}"

    else:
        # This is **not** the local project, but no --name was given.
        # NOTE: `--version` is not required when using local dependencies.
        cli_ctx.abort("Must provide --name")

    if log_name:
        cli_ctx.logger.success(f"Package '{log_name}' installed.")
    else:
        cli_ctx.logger.success("All project packages installed.")


@cli.command()
@ape_cli_context()
@click.argument("name")
@click.option("--version", help="The dependency version", metavar="VERSION")
@click.option("--force", "-f", help="Force a re-compile", is_flag=True)
def compile(cli_ctx, name, version, force):
    """
    Compile a package
    """

    if name not in cli_ctx.project_manager.dependencies:
        cli_ctx.abort(f"Dependency '{name}' unknown. Is it installed?")

    versions = cli_ctx.project_manager.dependencies[name]
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

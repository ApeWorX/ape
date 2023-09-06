import json
from pathlib import Path
from typing import Tuple

import click

from ape.cli import ape_cli_context


@click.group()
def cli():
    """
    Package management tools
    """


def _echo_no_packages(project: bool):
    message = "No packages installed"
    if project:
        message = f"{message} for this project"

    click.echo(f"{message}.")


@cli.command("list")
@ape_cli_context()
@click.option(
    "_all", "--all", is_flag=True, help="Include packages not referenced by the local project"
)
def _list(cli_ctx, _all):
    """
    List installed packages
    """

    packages = []
    if _all:
        location = cli_ctx.dependency_manager.DATA_FOLDER / "packages"
        if not location.is_dir():
            _echo_no_packages(False)
            return

        for dependency in location.iterdir():
            base_item = {"name": dependency.name}
            for version_dir in dependency.iterdir():
                item = {"version": version_dir.name, **base_item}
                file = next(version_dir.iterdir(), None)
                item["compiled"] = (
                    bool(json.loads(file.read_text()).get("contractTypes")) if file else False
                )
                packages.append(item)

    else:
        # Limit to local project.
        for name, versions in cli_ctx.project_manager.dependencies.items():
            base_item = {"name": name}
            for version, dep in versions.items():
                item = {**base_item, "version": version, "compiled": bool(dep.contract_types)}
                packages.append(item)

    if not packages:
        _echo_no_packages(not _all)
        return

    # Output gathered packages.
    click.echo("Packages:")
    for package in packages:
        name = click.style(package["name"], bold=True)
        version = package["version"]
        compiled = click.style(package["compiled"], fg="green") if package.get("compiled") else ""
        click.echo(f"  {name} {version}{' '  + compiled if compiled else ''}")


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

    elif value == ".":
        return value

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
    help="A reference flag, used for GitHub branches or tags instead of version",
    metavar="REF",
)
@click.option("--force", "-f", help="Force a re-install", is_flag=True)
def install(cli_ctx, package, name, version, ref, force):
    """
    Download and cache packages
    """

    log_name = None

    if not package or package == ".":
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
@click.argument("package", nargs=1, required=True)
@click.argument("versions", nargs=-1, required=False)
@click.option(
    "-y", "--yes", is_flag=True, help="Automatically confirm the removal of the package(s)"
)
def remove(cli_ctx, package, versions, yes):
    """
    Remove a package

    This command removes a package from the installed packages.

    If specific versions are provided, only those versions of the package will be
    removed. If no versions are provided, the command will prompt you to choose
    versions to remove. You can also choose to remove all versions of the package.

    Examples:\n
    - Remove specific versions: ape pm remove <PackageName> "1.0.0" "2.0.0"\n
    - Prompt to choose versions: ape pm remove <PackageName>\n
    - Remove all versions: ape pm remove <PackageName> -y
    """
    package_dir = cli_ctx.dependency_manager.DATA_FOLDER / "packages" / package
    if not package_dir.is_dir():
        cli_ctx.abort(f"Package '{package}' is not installed.")

    # Remove multiple versions if no version is specified
    versions_to_remove = versions if versions else []
    if len(versions_to_remove) == 1 and versions_to_remove[0] == "all":
        versions_to_remove = [d.name for d in package_dir.iterdir() if d.is_dir()]

    elif not versions_to_remove:
        available_versions = [d.name for d in package_dir.iterdir() if d.is_dir()]
        if not available_versions:
            cli_ctx.abort(f"No installed versions of package '{package}' found.")

        # If there is only one version, use that.
        if len(available_versions) == 1 or yes:
            versions_to_remove = available_versions

        else:
            version_prompt = (
                f"Which versions of package '{package}' do you want to remove? "
                f"{available_versions} (separate multiple versions with comma, or 'all')"
            )
            versions_input = click.prompt(version_prompt)
            if versions_input.strip() == "all":
                versions_to_remove = available_versions
            else:
                versions_to_remove = [v.strip() for v in versions_input.split(",") if v.strip()]

            # Prevents a double-prompt.
            yes = True

    if not versions_to_remove:
        cli_ctx.logger.info("No versions selected for removal.")
        return

    # Remove all the versions specified
    for version in versions_to_remove:
        if not (package_dir / version).is_dir() and not (package_dir / f"v{version}").is_dir():
            cli_ctx.logger.warning(
                f"Version '{version}' of package '{package_dir.name}' is not installed."
            )
            continue

        elif yes or click.confirm(
            f"Are you sure you want to remove version '{version}' of package '{package}'?"
        ):
            cli_ctx.project_manager.remove_dependency(package_dir.name, versions=[version])
            cli_ctx.logger.success(f"Version '{version}' of package '{package_dir.name}' removed.")


@cli.command()
@ape_cli_context()
@click.argument("name", nargs=1, required=False)
@click.option("--version", help="The dependency version", metavar="VERSION")
@click.option("--force", "-f", help="Force a re-compile", is_flag=True)
def compile(cli_ctx, name, version, force):
    """
    Compile a package
    """

    if not name:
        # Compile all local project dependencies.
        for dep_name, versions in cli_ctx.project_manager.dependencies.items():
            for version, dependency in versions.items():
                log_line = dep_name
                if version != "local":
                    log_line += f"@{version}"

                try:
                    dependency.compile(use_cache=not force)
                except Exception as err:
                    cli_ctx.logger.error(err)
                else:
                    cli_ctx.logger.success(f"Package '{log_line}' compiled.")

        return

    elif name not in cli_ctx.project_manager.dependencies:
        cli_ctx.abort(f"Dependency '{name}' unknown. Is it installed?")

    if not (versions := cli_ctx.project_manager.dependencies[name]):
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
        cli_ctx.abort(f"Version '{version}' for dependency '{name}' not found. Is it installed?")

    dependency = versions[version_found]

    try:
        dependency.compile(use_cache=not force)
    except Exception as err:
        cli_ctx.logger.error(err)
    else:
        log_line = name
        if version_found and version_found != "local":
            log_line = f"{log_line}@{version_found}"

        cli_ctx.logger.success(f"Package '{log_line}' compiled.")

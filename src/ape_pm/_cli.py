import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import click

from ape.cli.options import ape_cli_context, config_override_option
from ape.exceptions import ProjectError
from ape.logging import logger

if TYPE_CHECKING:
    from ape.managers.project import Dependency


@click.group()
def cli():
    """
    Package management tools
    """


@cli.command("list")
@ape_cli_context()
@click.option("--all", "list_all", help="List all installed dependencies", is_flag=True)
def _list(cli_ctx, list_all):
    """
    List installed packages
    """

    dm = cli_ctx.dependency_manager
    packages = []
    dependencies = [*list(dm.get_project_dependencies(use_cache=True, allow_install=False))]
    if list_all:
        dependencies = list({*dependencies, *dm.installed})

    for dependency in dependencies:
        if dependency.installed:
            is_installed = True
            try:
                is_compiled = dependency.project.is_compiled
            except ProjectError:
                # Project may not even be installed right.
                is_compiled = False

        else:
            is_installed = False
            is_compiled = False

        # For local dependencies, use the short name.
        # This is mostly because it looks nicer than very long paths.
        dependency_module = import_module("ape_pm.dependency")
        name = (
            dependency.name
            if isinstance(dependency.api, dependency_module.LocalDependency)
            else dependency.package_id
        )

        item = {
            "name": name,
            "version": dependency.version,
            "installed": is_installed,
            "compiled": is_compiled,
        }
        packages.append(item)

    if not packages:
        if list_all:
            click.echo("No packages installed.")
        else:
            click.echo("No packages installed. Use `--all` to list all installed dependencies.")
        return

    # Output gathered packages.
    longest_name = max([4, *[len(p["name"]) for p in packages]])
    longest_version = max([7, *[len(p["version"]) for p in packages]])
    longest_installed = max([9, *[len(f"{p['installed']}") for p in packages]])
    tab = "  "

    header_name_space = ((longest_name - len("NAME")) + 2) * " "
    version_name_space = ((longest_version - len("VERSION")) + 2) * " "

    def get_package_str(_package) -> str:
        dep_name = click.style(_package["name"], bold=True)
        version = _package["version"]
        installed = (
            click.style(_package["installed"], fg="green") if _package.get("installed") else "False"
        )
        compiled = (
            click.style(_package["compiled"], fg="green") if _package.get("compiled") else "False"
        )
        spacing_name = ((longest_name - len(_package["name"])) + len(tab)) * " "
        spacing_version = ((longest_version - len(version)) + len(tab)) * " "
        spacing_installed = ((longest_installed - len(f"{_package['installed']}")) + len(tab)) * " "
        return (
            f"{dep_name}{spacing_name}{version}{spacing_version}"
            f"{installed}{spacing_installed}{compiled}"
        )

    def rows():
        yield f"NAME{header_name_space}VERSION{version_name_space}INSTALLED  COMPILED\n"
        for _package in sorted(packages, key=lambda p: f"{p['name']}{p['version']}"):
            yield f"{get_package_str(_package)}\n"

    if len(packages) > 16:
        click.echo_via_pager(rows())
    else:
        for row in rows():
            click.echo(row.strip())


def _handle_package_path(path: Path, original_value: Optional[str] = None) -> dict:
    if not path.exists():
        value = original_value or path.as_posix()
        raise click.BadArgumentUsage(f"Unknown package '{value}'.")

    elif path.is_file() and (path.stem == "ape-config" or path.name == "pyproject.toml"):
        path = path.parent

    path = path.resolve().absolute()
    return {"local": path.as_posix()}


def _package_callback(ctx, param, value):
    if value is None:
        # Install all packages from local project.
        return None

    elif isinstance(value, Path):
        return _handle_package_path(value)

    elif value.startswith("gh:"):
        # Is a GitHub style dependency
        return {"github": value[3:]}

    elif value.startswith("npm:"):
        # Is an NPM style dependency
        return {"npm": value[4:]}

    elif value == ".":
        return value

    # Check if is a local package.
    try:
        path = Path(value).absolute()
    except Exception:
        pass
    else:
        return _handle_package_path(path, original_value=value)

    if isinstance(value, str) and ":" in value:
        # Catch-all for unknown dependency types that may exist.
        parts = value.split(":")
        return {parts[0]: parts[1]}

    raise click.BadArgumentUsage(f"Unknown package '{value}'.")


@cli.command()
@ape_cli_context()
@click.argument("package", required=False, callback=_package_callback)
@click.option("--name", help="The name of the dependency", metavar="NAME")
@click.option("--version", help="The dependency's version", metavar="VERSION")
@click.option(
    "--ref",
    help="A reference flag, used for GitHub branches or tags instead of version",
    metavar="REF",
)
@click.option("--force", "-f", help="Force a re-install", is_flag=True)
@config_override_option()
def install(cli_ctx, package, name, version, ref, force, config_override):
    """
    Download and cache packages
    """

    pm = cli_ctx.local_project
    if not package or package == ".":
        if version:
            cli_ctx.abort("Cannot specify version when installing from config.")

        pm.dependencies.install(use_cache=not force)
        message = "All project packages installed."
        if not force:
            message = f"{message} Use `--force` to re-install."

        cli_ctx.logger.success(message)
        return

    if name:
        package["name"] = name
    if ref:
        package["ref"] = ref
    if version:
        package["version"] = version
    if config_override:
        package["config_override"] = config_override

    try:
        dependency = pm.dependencies.install(**package, use_cache=not force)
    except Exception as err:
        cli_ctx.logger.log_error(err)
    else:
        cli_ctx.logger.success(f"Package '{dependency.name}@{dependency.version}' installed.")


@cli.command()
@ape_cli_context()
@click.argument("name", required=False)
@click.argument("versions", nargs=-1, required=False)
@click.option(
    "-y", "--yes", is_flag=True, help="Automatically confirm the removal of the package(s)"
)
def uninstall(cli_ctx, name, versions, yes):
    """
    Uninstall a package

    This command removes a package from the installed packages.

    If specific versions are provided, only those versions of the package will be
    removed. If no versions are provided, the command will prompt you to choose
    versions to remove. You can also choose to remove all versions of the package.

    Examples:\n
    - Remove specific versions: ape pm uninstall <PackageName> "1.0.0" "2.0.0"\n
    - Prompt to choose versions: ape pm uninstall <PackageName>\n
    - Remove all versions: ape pm uninstall <PackageName> -y
    """

    pm = cli_ctx.local_project

    # NOTE: Purposely don't call `get_dependency` or anything so we for sure
    #   are only checking the installed.
    installed = {d for d in pm.dependencies.installed}

    did_error = False
    did_find = False

    if not name or name == ".":
        if versions:
            cli_ctx.abort("Cannot specify version when uninstalling from config.")

        # Uninstall all dependencies from the config.
        for cfg in pm.config.dependencies:
            api = pm.dependencies.decode_dependency(**cfg)
            for dependency in installed:
                if dependency.name != api.name or dependency.version != api.version_id:
                    continue

                did_find = True
                res = _uninstall(dependency, yes=yes)
                if res is False:
                    did_error = True

    else:
        deps_to_remove = {
            d
            for d in installed
            if (d.name == name or d.package_id == name)
            and (d.version in versions if versions else True)
        }
        for dependency in deps_to_remove:
            did_find = True
            res = _uninstall(dependency, yes=yes)
            if res is False:
                did_error = True

    if not did_find:
        if name:
            name = ", ".join([f"{name}={v}" for v in versions]) if versions else name
            cli_ctx.logger.error(f"Package(s) '{name}' not installed.")
        else:
            cli_ctx.logger.error(
                "No package(s) installed in local project. "
                "Please specify a package to uninstall or go to a local project."
            )

        did_error = True

    sys.exit(int(did_error))


def _uninstall(dependency: "Dependency", yes: bool = False) -> bool:
    key = f"{dependency.name}={dependency.version}"
    if not yes and not click.confirm(f"Remove '{key}'"):
        return True  # Not an error.

    try:
        dependency.uninstall()
    except Exception as err:
        logger.error(f"Failed uninstalling '{key}': {err}")
        return False

    logger.success(f"Uninstalled '{key}'.")
    return True


@cli.command()
@ape_cli_context()
@click.argument("name", required=False)
@click.option("--version", help="The dependency version", metavar="VERSION")
@click.option("--force", "-f", help="Force a re-compile", is_flag=True)
@config_override_option()
def compile(cli_ctx, name, version, force, config_override):
    """
    Compile a package
    """
    pm = cli_ctx.local_project
    if not name or name == ".":
        if version:
            cli_ctx.abort("Cannot specify 'version' without 'name'.")

        # Compile all from config.
        did_error = False
        for cfg in pm.config.dependencies:
            if config_override:
                cfg["config_override"] = config_override

            dependency = pm.dependencies.install(**cfg)
            _compile_dependency(cli_ctx, dependency, force)

        if did_error:
            sys.exit(1)

        return

    if version:
        to_compile = [pm.dependencies.get_dependency(name, version)]
    else:
        to_compile = [d for d in pm.dependencies.get_versions(name)]

    if not to_compile:
        key = f"{name}@{version}" if version else name
        cli_ctx.abort(f"Dependency '{key}' unknown. Is it installed?")

    for dependency in to_compile:
        if config_override:
            dependency.api.config_override = config_override

        _compile_dependency(cli_ctx, dependency, force)


def _compile_dependency(cli_ctx, dependency: "Dependency", force: bool):
    try:
        result = dependency.compile(use_cache=not force)
    except Exception as err:
        cli_ctx.logger.error(str(err))
    else:
        if result:
            cli_ctx.logger.success(f"Package '{dependency.name}@{dependency.version}' compiled.")
        # else: user should have received warning from `dependency.compile()` if there
        # was no result.

import sys
from pathlib import Path

import click

from ape.cli.options import ape_cli_context, config_override_option


@click.group()
def cli():
    """
    Package management tools
    """


@cli.command("list")
@ape_cli_context()
def _list(cli_ctx):
    """
    List installed packages
    """

    pm = cli_ctx.project_manager
    packages = []
    for dependency in pm.dependencies:
        item = {
            "name": dependency.name,
            "version": dependency.version,
            "compiled": dependency.project.is_compiled,
        }
        packages.append(item)

    if not packages:
        click.echo("No packages installed.")
        return

    # Output gathered packages.
    longest_name = max([4, *[len(p["name"]) for p in packages]])
    longest_version = max([7, *[len(p["version"]) for p in packages]])
    tab = "  "

    header_name_space = ((longest_name - len("NAME")) + 2) * " "
    version_name_space = ((longest_version - len("VERSION")) + 2) * " "

    def get_package_str(_package) -> str:
        name = click.style(_package["name"], bold=True)
        version = _package["version"]
        compiled = (
            click.style(_package["compiled"], fg="green") if _package.get("compiled") else "-"
        )
        spacing_name = ((longest_name - len(_package["name"])) + len(tab)) * " "
        spacing_version = ((longest_version - len(version)) + len(tab)) * " "
        return f"{name}{spacing_name}{version}{spacing_version + compiled}"

    def rows():
        yield f"NAME{header_name_space}VERSION{version_name_space}COMPILED\n"
        for _package in packages:
            yield f"{get_package_str(_package)}\n"

    if len(packages) > 16:
        click.echo_via_pager(rows())
    else:
        for row in rows():
            click.echo(row.strip())


def _package_callback(ctx, param, value):
    if value is None:
        # Install all packages from local project.
        return None

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
@click.argument("package", required=False, callback=_package_callback)
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

    pm = cli_ctx.project_manager
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

    try:
        api = pm.dependencies.decode_dependency(package)
    except Exception as err:
        # Invalid API data.
        cli_ctx.logger.log_error(err)
    else:
        pm.dependencies.install(api, use_cache=not force)
        cli_ctx.logger.success(f"Package '{api.name}@{api.version_id}' installed.")


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
    - Remove specific versions: ape pm remove <PackageName> "1.0.0" "2.0.0"\n
    - Prompt to choose versions: ape pm remove <PackageName>\n
    - Remove all versions: ape pm remove <PackageName> -y
    """

    pm = cli_ctx.project_manager
    if not name or name == ".":
        if versions:
            cli_ctx.abort("Cannot specify version when uninstalling from config.")

        # Uninstall all dependencies from the config.
        names = [x["name"] for x in pm.config.dependencies]
    else:
        names = [name]

    did_error = False
    did_find = False
    for name in names:
        if versions:
            for version in versions:
                dependency = pm.dependencies.get_dependency(name, version)
                did_find = True
                key = f"{name}={version}"
                if yes or click.confirm(f"Remove '{key}'"):
                    try:
                        dependency.uninstall()
                    except Exception as err:
                        cli_ctx.logger.error(f"Failed uninstalling '{key}': {err}")
                        did_error = True
                        continue
                    else:
                        cli_ctx.logger.success(f"Uninstalled '{key}'.")

        else:
            # Remove all versions.
            for dependency in pm.dependencies:
                key = f"{name}={dependency.version}"
                if dependency.name == name:
                    did_find = True
                    if yes or click.confirm(f"Remove '{key}'"):
                        try:
                            dependency.uninstall()
                        except Exception as err:
                            cli_ctx.logger.error(f"Failed uninstalling '{key}': {err}")
                            did_error = True
                            continue
                        else:
                            cli_ctx.logger.success(f"Uninstalled '{key}'.")

        if not did_find:
            name = ", ".join([f"{name}={v}" for v in versions]) if versions else name
            cli_ctx.logger.error(f"Package(s) '{name}' not installed.")
            did_error = True

        if did_error:
            sys.exit(1)


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

    pm = cli_ctx.project_manager
    if not name or name == ".":
        if version:
            cli_ctx.abort("Cannot specify 'version' without 'name'.")

        # Compile all from config.
        did_error = False
        for cfg in pm.config.dependencies:
            if config_override:
                cfg["config_override"] = config_override

            api = pm.dependencies.decode_dependency(cfg)
            pm.dependencies.install(api)
            dependency = pm.dependencies.get_dependency(api.name, api.version_id)

            try:
                dependency.compile(use_cache=not force)
            except Exception as err:
                cli_ctx.logger.error(str(err))
                continue
            else:
                cli_ctx.logger.success(f"Package '{api.name}@{api.version_id}' compiled.")

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
            dependency.config_override = config_override

        try:
            dependency.compile(use_cache=not force)
        except Exception as err:
            cli_ctx.logger.error(str(err))
            continue
        else:
            cli_ctx.logger.success(f"Package '{dependency.name}@{dependency.version}' compiled.")

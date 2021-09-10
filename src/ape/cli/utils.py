import click


class Abort(click.ClickException):
    """Wrapper around a CLI exception"""

    def show(self, file=None):
        """Override default ``show`` to print CLI errors in red text."""
        notify("ERROR", self.format_message())


NOTIFY_COLORS = {
    "WARNING": "bright_red",
    "ERROR": "bright_red",
    "SUCCESS": "bright_green",
    "INFO": "blue",
}


def notify(type_, msg):
    """Prepends a message with a colored tag and outputs it to the console."""
    click.echo(f"{click.style(type_, fg=NOTIFY_COLORS[type_])}: {msg}", err=type_ == "ERROR")


__all__ = ["Abort", "notify"]

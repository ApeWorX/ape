import click

NOTIFY_COLORS = {"WARNING": "bright_red", "ERROR": "bright_red", "SUCCESS": "bright_green"}


def notify(type_, msg):
    """Prepends a message with a colored tag and outputs it to the console."""
    click.echo(f"{click.style(type_, fg=NOTIFY_COLORS[type_])}: {msg}")

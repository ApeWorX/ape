# Logging

Ape provides a logger and uses it to show messages throughout the execution of its modules.
Every CLI command comes with the logger in Ape, even custom user scripts (unless they change the behavior of `--verbosity`).

The following log levels are available with Ape:

| Log Level | Numeric Value | Purpose                        | Color  |
| --------- | ------------- | ------------------------------ | ------ |
| DEBUG     | 10            | Debug stuff                    | Blue   |
| INFO      | 20            | General information            | Blue   |
| SUCCESS   | 21            | To mark a successful operation | Green  |
| WARNING   | 30            | Indicates a potential issue    | Yellow |
| ERROR     | 40            | An error occurred              | Red    |

```{note}
`SUCCESS` is a non-standard verbosity level custom to the framework.
It is shown during `INFO` but not shown if set to `WARNING` or above.
```

## CLI Logging

If you are running into issues and wish to see more information logged, you likely want to run your command with `--verbosity DEBUG` or `-v debug`:

```bash
ape --verbosity DEBUG my_cmd  # long form
ape -v debug my_cmd           # short form
```

This will output HTTP requests and anything else with a `DEBUG` logging verbosity in Ape.

Alternatively, you may wish to log less and show important logs, such as `ERROR` logs.
To do this, use the `ERROR` verbosity:

```bash
ape my_cmd -v ERROR 
```

*NOTE*: You can put the verbosity flag anywhere in your CLI command for _most_ commands.

## Python Logging

You can also import and use the logger in your own Python scripts or commands:

```python
from ape.logging import logger, LogLevel

def main():
    logger.info("You have entered `main()`.")
    logger.set_level(LogLevel.WARNING)
```

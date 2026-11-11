from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from ape.utils.basemodel import BaseInterfaceModel

if TYPE_CHECKING:
    import click


class ScriptRunnerAPI(BaseInterfaceModel):
    """
    Script runner plugins turn script files of another language, such as Foundry's
    ``.s.sol`` scripts, into ``ape run`` commands.

    See the `ape-foundry <https://github.com/ApeWorX/ape-foundry>`__ plugin for an example
    implementation of this API.
    """

    @property
    def scripts_folder_name(self) -> str:
        """
        The project folder, besides ``scripts/``, that holds this runner's scripts.
        Defaults to ``scripts``.
        """
        return "scripts"

    @abstractmethod
    def get_command(self, script_path: Path, name: str) -> "click.Command | None":
        """
        The ``ape run`` command for the given script.

        Args:
            script_path (Path): The script file.
            name (str): The command name, the file name without the runner's extension.

        Returns:
            click.Command | None: The command, or ``None`` when the file is not a runnable
            script.
        """

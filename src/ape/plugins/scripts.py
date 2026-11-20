from typing import TYPE_CHECKING

from .pluggy_patch import PluginType, hookspec

if TYPE_CHECKING:
    from ape.api.scripts import ScriptRunnerAPI


class ScriptRunnerPlugin(PluginType):
    """
    A plugin that implements the :class:`ape.api.scripts.ScriptRunnerAPI`, so ``ape run``
    can run scripts written in another language, such as Foundry scripts in
    `ape-foundry <https://github.com/ApeWorX/ape-foundry>`__.
    """

    @hookspec
    def register_script_runner(  # type: ignore[empty-body]
        self,
    ) -> tuple[tuple[str, ...], type["ScriptRunnerAPI"]]:
        """
        A hook for returning the script file extensions the plugin runs and the runner
        class that turns them into ``ape run`` commands.

        Usage example::

            @plugins.register(plugins.ScriptRunnerPlugin)
            def register_script_runner():
                return (".s.sol",), ForgeScriptRunner

        Returns:
            tuple[tuple[str, ...], type[:class:`~ape.api.scripts.ScriptRunnerAPI`]]
        """

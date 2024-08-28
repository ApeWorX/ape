from collections.abc import Callable

import requests
from requests.models import CaseInsensitiveDict
from tqdm import tqdm  # type: ignore

from ape.exceptions import ProviderNotConnectedError
from ape.logging import logger
from ape.utils.misc import __version__, _python_version

USER_AGENT = f"Ape/{__version__} (Python/{_python_version})"


def allow_disconnected(fn: Callable):
    """
    A decorator that instead of raising :class:`~ape.exceptions.ProviderNotConnectedError`
    warns and returns ``None``.

    Usage example::

        from typing import Optional
        from ape.types import SnapshotID
        from ape.utils import return_none_when_disconnected

        @allow_disconnected
        def try_snapshot(self) -> Optional[SnapshotID]:
            return self.chain.snapshot()

    """

    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ProviderNotConnectedError:
            logger.warning("Provider is not connected.")
            return None

    return inner


def stream_response(download_url: str, progress_bar_description: str = "Downloading") -> bytes:
    """
    Download HTTP content by streaming and returning the bytes.
    Progress bar will be displayed in the CLI.

    Args:
        download_url (str): String to get files to download.
        progress_bar_description (str): Downloading word.

    Returns:
        bytes: Content in bytes to show the progress.
    """
    response = requests.get(download_url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    progress_bar = tqdm(total=total_size, unit="iB", unit_scale=True, leave=False)
    progress_bar.set_description(progress_bar_description)
    content = b""
    for data in response.iter_content(1024, decode_unicode=True):
        progress_bar.update(len(data))
        content += data

    progress_bar.close()
    return content


class RPCHeaders(CaseInsensitiveDict):
    """
    A dict-like data-structure for HTTP-headers.
    It is case-insensitive and appends user-agent strings
    rather than overrides.
    """

    def __setitem__(self, key, value):
        if key.lower() != "user-agent" or not self.__contains__("user-agent"):
            return super().__setitem__(key, value)

        # Handle appending the user-agent (without replacing).
        existing_user_agent = self.__getitem__("user-agent")
        parts = [a.strip() for a in value.split(" ")]
        new_parts = []
        for part in parts:
            if part in existing_user_agent:
                # Already added.
                continue
            else:
                new_parts.append(part)

        if new_user_agent := " ".join(new_parts):
            super().__setitem__(key, f"{existing_user_agent} {new_user_agent}")

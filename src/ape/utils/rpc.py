import time
from collections.abc import Callable
from random import randint
from typing import Optional

import requests
from requests.models import CaseInsensitiveDict
from tqdm import tqdm  # type: ignore

from ape.exceptions import ProviderError, ProviderNotConnectedError
from ape.logging import logger
from ape.utils.misc import __version__, _python_version

USER_AGENT: str = f"Ape/{__version__} (Python/{_python_version})"


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


def request_with_retry(
    func: Callable,
    min_retry_delay: int = 1_000,
    retry_backoff_factor: int = 2,
    max_retry_delay: int = 30_000,
    max_retries: int = 10,
    retry_jitter: int = 250,
    is_rate_limit: Optional[Callable[[Exception], bool]] = None,
):
    """
    Make a request with 429/rate-limit retry logic.

    Args:
        func (Callable): The function to run with rate-limit handling logic.
        min_retry_delay (int): The amount of milliseconds to wait before
          retrying the request. Defaults to ``1_000`` (one second).
        retry_backoff_factor (int): The multiplier applied to the retry delay
          after each failed attempt. Defaults to ``2``.
        max_retry_delay (int): The maximum length of the retry delay.
          Defaults to ``30_000`` (30 seconds).
        max_retries (int): The maximum number of retries.
          Defaults to ``10``.
        retry_jitter (int): A random number of milliseconds up to this limit
          is added to each retry delay. Defaults to ``250`` milliseconds.
        is_rate_limit (Callable[[Exception], bool] | None): A custom handler
          for detecting rate-limits. Defaults to checking for a 429 status
          code on an HTTPError.
    """
    if not is_rate_limit:
        # Use default checker.
        def checker(err: Exception) -> bool:
            return isinstance(err, requests.HTTPError) and err.response.status_code == 429

        is_rate_limit = checker

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as err:
            if not is_rate_limit(err):
                # It was not a rate limit error. Raise whatever exception it is.
                raise

            else:
                # We were rate-limited. Invoke retry/backoff logic.
                logger.warning("Request was rate-limited. Backing-off and then retrying...")
                retry_interval = min(
                    max_retry_delay, min_retry_delay * retry_backoff_factor**attempt
                )
                delay = retry_interval + randint(0, retry_jitter)
                time.sleep(delay / 1000)
                continue

    # If we get here, we over-waited. Raise custom exception.
    raise ProviderError(f"Rate limit retry-mechanism exceeded after '{max_retries}' attempts.")

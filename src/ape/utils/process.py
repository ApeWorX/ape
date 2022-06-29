import queue
import threading
import time

from ape.exceptions import SubprocessTimeoutError


class JoinableQueue(queue.Queue):
    """
    A queue that can be joined, useful for multi-processing.
    Borrowed from the ``py-geth`` library.
    """

    def __iter__(self):
        while True:
            item = self.get()

            is_stop_iteration_type = isinstance(item, type) and issubclass(item, StopIteration)
            if isinstance(item, StopIteration) or is_stop_iteration_type:
                return

            elif isinstance(item, Exception):
                raise item

            elif isinstance(item, type) and issubclass(item, Exception):
                raise item

            yield item

    def join(self, timeout=None):
        with SubprocessTimeoutError(timeout) as _timeout:
            while not self.empty():
                time.sleep(0)
                _timeout.check()


def spawn(target, *args, **kwargs):
    """
    Spawn a new daemon thread. Borrowed from the ``py-geth`` library.
    """

    thread = threading.Thread(
        target=target,
        args=args,
        kwargs=kwargs,
    )
    thread.daemon = True
    thread.start()
    return thread

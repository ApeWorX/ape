import functools
import inspect
from collections.abc import Callable
from typing import Any


def network_context() -> Callable:
    """
    A decorator that wraps a FastAPI route handler to automatically
    enter the correct Ape network context.

    ``ecosystem`` and ``network`` are injected as FastAPI Query parameters
    automatically — you do not need to declare them in the function signature.
    If you do declare them, they will still be passed through to your function.

    Example (without declaring ecosystem/network)::

        @app.post("/faucet/{token}")
        @network_context()
        def send_token(token: str, receiver: str, amount: int) -> str:
            # Ape is connected to the network requested via query string
            # e.g. ?ecosystem=ethereum&network=mainnet
            ...

    Example (with ecosystem/network in signature)::

        @app.post("/faucet/{token}")
        @network_context()
        def send_token(token: str, ecosystem: str, network: str) -> str:
            print(f"Connected to {ecosystem}:{network}")
            ...

    Raises:
        :class:`~ape.exceptions.NetworkError`: When the given ecosystem/network
            combination does not match any known network.
        ``ImportError``: When ``fastapi`` is not installed.
    """

    def decorator(func: Callable) -> Callable:
        original_params = inspect.signature(func).parameters

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ecosystem = kwargs.get("ecosystem")
            network = kwargs.get("network")

            network_choice = f"{ecosystem}:{network}"

            # Import here so fastapi remains an optional dependency.
            # ape.networks is also imported here to avoid circular imports
            # at module load time.
            from ape import networks

            with networks.parse_network_choice(network_choice):
                # Only strip ecosystem/network from kwargs if the original
                # function does not declare them — otherwise pass them through.
                call_kwargs = dict(kwargs)
                if "ecosystem" not in original_params:
                    call_kwargs.pop("ecosystem", None)
                if "network" not in original_params:
                    call_kwargs.pop("network", None)

                return func(*args, **call_kwargs)

        try:
            from fastapi import Query
        except ImportError as e:
            raise ImportError(
                "fastapi is required to use ape.ext.fastapi. Install it with: pip install fastapi"
            ) from e

        original_sig = inspect.signature(func)
        extra_params: list[inspect.Parameter] = []

        if "ecosystem" not in original_params:
            extra_params.append(
                inspect.Parameter(
                    "ecosystem",
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=Query(..., description="Ape ecosystem name, e.g. 'ethereum'"),
                    annotation=str,
                )
            )

        if "network" not in original_params:
            extra_params.append(
                inspect.Parameter(
                    "network",
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=Query(..., description="Ape network name, e.g. 'mainnet'"),
                    annotation=str,
                )
            )

        if extra_params:
            existing = list(original_sig.parameters.values())
            # Insert extra params before **kwargs (VAR_KEYWORD) if present,
            # since **kwargs must always be the last parameter in a signature.
            insert_at = len(existing)
            for i, p in enumerate(existing):
                if p.kind == inspect.Parameter.VAR_KEYWORD:
                    insert_at = i
                    break

            new_params = existing[:insert_at] + extra_params + existing[insert_at:]
            wrapper.__signature__ = original_sig.replace(parameters=new_params)  # type: ignore[attr-defined]

        return wrapper

    return decorator

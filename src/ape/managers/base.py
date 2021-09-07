from pydantic import BaseModel

from ape.utils import cached_property


class BaseManager(BaseModel):
    class Config:
        keep_untouched = (cached_property,)

    # NOTE: Due to https://github.com/samuelcolvin/pydantic/issues/1241
    #       we have to add this cached property workaround in order to avoid this error:
    #
    #           TypeError: cannot pickle '_thread.RLock' object

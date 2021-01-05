# NOTE: This file only executes once on module load
import shutil
from pathlib import Path

from .constants import (
    INSTALL_FOLDER,
    DATA_FOLDER,
    DATA_SUBFOLDERS,
)


# create data folder structure
DATA_FOLDER.mkdir(exist_ok=True)
for folder in DATA_SUBFOLDERS:
    DATA_FOLDER.joinpath(folder).mkdir(exist_ok=True)

if not DATA_FOLDER.joinpath("network-config.yaml").exists():
    shutil.copyfile(
        INSTALL_FOLDER.joinpath("data/network-config.yaml"),
        DATA_FOLDER.joinpath("network-config.yaml"),
    )

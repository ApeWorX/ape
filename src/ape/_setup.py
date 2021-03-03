# NOTE: This file only executes once on module load
import shutil

from .constants import DATA_FOLDER, DATA_SUBFOLDERS, INSTALL_FOLDER

# create data folder structure
DATA_FOLDER.mkdir(exist_ok=True)
for folder in DATA_SUBFOLDERS:
    DATA_FOLDER.joinpath(folder).mkdir(exist_ok=True)

if not DATA_FOLDER.joinpath("network-config.yaml").exists():
    shutil.copyfile(
        INSTALL_FOLDER.joinpath("data/network-config.yaml"),
        DATA_FOLDER.joinpath("network-config.yaml"),
    )

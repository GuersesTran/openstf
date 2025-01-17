# SPDX-FileCopyrightText: 2017-2021 Alliander N.V. <korte.termijn.prognoses@alliander.com> # noqa E501>
#
# SPDX-License-Identifier: MPL-2.0

from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.absolute()

try:
    __version__ = version("openstf")
except PackageNotFoundError:
    # package is not installed
    pass

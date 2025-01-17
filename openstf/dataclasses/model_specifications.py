# SPDX-FileCopyrightText: 2021 2017-2021 Alliander N.V. <korte.termijn.prognoses@alliander.com>
#
# SPDX-License-Identifier: MPL-2.0

from pydantic import BaseModel
from typing import Optional, Union


class ModelSpecificationDataClass(BaseModel):
    id: Union[int, str]
    hyper_params: Optional[dict] = {}
    feature_names: Optional[list] = None

    def __getitem__(self, item):
        """Allows us to use subscription to get the items from the object"""
        return getattr(self, item)

    def __setitem__(self, key: str, value: any):
        """Allows us to use subscription to set the items in the object"""
        if hasattr(self, key):
            self.__dict__[key] = value
        else:
            raise AttributeError(f"{key} not an attribute of model specifications.")

# SPDX-FileCopyrightText: 2017-2021 Contributors to the OpenSTF project <korte.termijn.prognoses@alliander.com> # noqa E501>
#
# SPDX-License-Identifier: MPL-2.0

import unittest

import numpy as np
import pandas as pd

from openstf.feature_engineering.lag_features import generate_non_trivial_lag_times
from test.utils import BaseTestCase, TestData


class TestApplyFeaturesAditionalMinuteSpace(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.data = TestData.load("input_data_train.pickle")

    def test_additional_minutes_space(self):
        minute_space_list = generate_non_trivial_lag_times(self.data)
        self.assertEqual(minute_space_list, [1410, 2880])

    def test_empty_data_frame(self):
        minute_space_list = generate_non_trivial_lag_times(pd.DataFrame())
        self.assertEqual(minute_space_list, [])

    def test_no_peaks_in_correlation(self):
        data = pd.DataFrame()
        data["random_column_name"] = np.linspace(0, 1000, 1000, endpoint=False)
        minute_space_list = generate_non_trivial_lag_times(data)
        self.assertEqual(minute_space_list, [])


# Run all tests
if __name__ == "__main__":
    unittest.main()

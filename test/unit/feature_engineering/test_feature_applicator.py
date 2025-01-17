# SPDX-FileCopyrightText: 2017-2021 Alliander N.V. <korte.termijn.prognoses@alliander.com> # noqa E501>
#
# SPDX-License-Identifier: MPL-2.0
from unittest import TestCase

import numpy as np

from openstf.feature_engineering.feature_applicator import (
    TrainFeatureApplicator,
    OperationalPredictFeatureApplicator,
)
from test.utils import TestData


class TestFeatureApplicator(TestCase):
    def setUp(self) -> None:
        self.input_data = TestData.load("input_data.pickle")

    def test_train_feature_applicator_correct_order(self):
        # Test for expected column order of the output
        data_with_features = TrainFeatureApplicator(horizons=[0.25, 24.0]).add_features(
            self.input_data[["load"]]
        )
        self.assertEqual(data_with_features.columns.to_list()[0], "load")
        self.assertEqual(data_with_features.columns.to_list()[-1], "horizon")

    def test_train_feature_applicator_filter_features(self):
        # Test for expected column order of the output
        # Also check "horizons" is not in the output
        features = self.input_data.columns.to_list()[:15]
        data_with_features = TrainFeatureApplicator(
            horizons=[0.25, 24.0], feature_names=features
        ).add_features(self.input_data)

        self.assertIn("horizon", data_with_features.columns.to_list())
        self.assertListEqual(
            list(np.sort(features + ["horizon"])),
            list(np.sort(data_with_features.columns.to_list())),
        )

    def test_operational_feature_applicator_correct_order(self):
        # Test for expected column order of the output
        # Also check "horizons" is not in the output
        data_with_features = OperationalPredictFeatureApplicator(
            horizons=[0.25]
        ).add_features(self.input_data[["load"]])
        self.assertEqual(data_with_features.columns.to_list()[0], "load")
        self.assertTrue("horizon" not in data_with_features.columns.to_list())

    def test_operational_feature_applicator_one_horizon(self):
        # Test for expected column order of the output
        # Also check "horizons" is not in the output
        with self.assertRaises(ValueError):
            OperationalPredictFeatureApplicator(horizons=[0.25, 1.0]).add_features(
                self.input_data[["load"]]
            )
        with self.assertRaises(ValueError):
            OperationalPredictFeatureApplicator(horizons=[]).add_features(
                self.input_data[["load"]]
            )

    def test_operational_feature_applicator_filter_features(self):
        # Test for expected column order of the output
        # Also check "horizons" is not in the output
        features = self.input_data.columns.to_list()
        data_with_features = OperationalPredictFeatureApplicator(
            horizons=[0.25], feature_names=features
        ).add_features(self.input_data[["load"]])

        self.assertListEqual(
            list(np.sort(features)), list(np.sort(data_with_features.columns.to_list()))
        )

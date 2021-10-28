# SPDX-FileCopyrightText: 2017-2021 Contributors to the OpenSTF project <korte.termijn.prognoses@alliander.com> # noqa E501>
#
# SPDX-License-Identifier: MPL-2.0

from unittest import TestCase

import pandas as pd

from openstf.model.confidence_interval_applicator import ConfidenceIntervalApplicator


class MockModel:
    confidence_interval = pd.DataFrame()

    def predict(self, input, quantile):
        stdev_forecast = pd.DataFrame({"forecast": [5, 6, 7], "stdev": [0.5, 0.6, 0.7]})
        return stdev_forecast["stdev"].rename(quantile)


class TestConfidenceIntervalApplicator(TestCase):
    def setUp(self) -> None:
        self.quantiles = [0.9, 0.5, 0.6, 0.1]

    def test_add_quantiles_to_forecast(self):
        stdev_forecast = pd.DataFrame({"forecast": [5, 6, 7], "stdev": [0.5, 0.6, 0.7]})

        pj = {"quantiles": [0.01, 0.10, 0.25, 0.50, 0.75, 0.90, 0.99]}
        pp_forecast = ConfidenceIntervalApplicator(
            MockModel(), stdev_forecast
        )._add_quantiles_to_forecast_quantile_regression(
            stdev_forecast, pj["quantiles"]
        )

        expected_new_columns = [
            f"quantile_P{int(q * 100):02d}" for q in pj["quantiles"]
        ]

        for expected_column in expected_new_columns:
            self.assertTrue(expected_column in pp_forecast.columns)

    def test_add_quantiles_to_forecast_default(self):
        stdev_forecast = pd.DataFrame({"forecast": [5, 6, 7], "stdev": [0.5, 0.6, 0.7]})
        pj = {"quantiles": [0.01, 0.10, 0.25, 0.50, 0.75, 0.90, 0.99]}

        pp_forecast = ConfidenceIntervalApplicator(
            MockModel(), "TEST"
        )._add_quantiles_to_forecast_default(stdev_forecast, pj["quantiles"])

        expected_new_columns = [
            f"quantile_P{int(q * 100):02d}" for q in pj["quantiles"]
        ]

        for expected_column in expected_new_columns:
            self.assertTrue(expected_column in pp_forecast.columns)

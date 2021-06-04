# SPDX-FileCopyrightText: 2017-2021 Alliander N.V. <korte.termijn.prognoses@alliander.com> # noqa E501>
#
# SPDX-License-Identifier: MPL-2.0
from pathlib import Path

import pandas as pd
import pytz
from datetime import timedelta
import structlog
from openstf.enums import ForecastType
from openstf.feature_engineering.feature_applicator import (
    OperationalPredictFeatureApplicator,
)
from openstf.model.basecase import BaseCaseModel
from openstf.model.confidence_interval_applicator import (
    ConfidenceIntervalApplicatorBaseCase,
)
from openstf.pipeline.create_forecast_sklearn import generate_forecast_datetime_range
from openstf.postprocessing.postprocessing import (
    add_prediction_job_properties_to_forecast,
)
from openstf.validation import validation

MODEL_LOCATION = Path(".")
BASECASE_HORIZON = 60 * 24 * 14  # 14 days ahead
BASECASE_RESOLUTION = 15

logger = structlog.get_logger(__name__)


def basecase_pipeline(pj: dict, input_data: pd.DataFrame) -> pd.DataFrame:
    """Computes the forecasts and confidence intervals given a prediction job and input data.


    Args:
        pj: (dict) prediction job
        input_data (pandas.DataFrame): data frame containing the input data necessary for the prediction.

    Returns:
        forecast (pandas.DataFrame)
    """

    logger = structlog.get_logger(__name__)

    # Validate and clean data
    validated_data = validation.validate(input_data)

    # Prep forecast input by selecting only the forecast datetime interval
    forecast_start, forecast_end = generate_forecast_datetime_range(
        BASECASE_RESOLUTION, BASECASE_HORIZON
    )

    # Dont forecast the horizon of the regular models
    forecast_start = forecast_start + timedelta(minutes=pj["horizon_minutes"])

    # Make sure forecast interval is available in the input interval
    validated_data = validated_data.reindex(
        pd.date_range(
            validated_data.index.min().to_pydatetime(),
            forecast_end.replace(tzinfo=pytz.utc),
            freq=f'{pj["resolution_minutes"]}T',
        )
    )

    # Add features
    data_with_features = OperationalPredictFeatureApplicator(
        horizons=[0.25],
        feature_names=["T-7d", "T-14d"],
    ).add_features(validated_data)

    # Select the basecase forecast interval
    forecast_input_data = data_with_features[forecast_start:forecast_end]

    # Initialize model
    model = BaseCaseModel()

    # Make basecase forecast
    basecase_forecast = BaseCaseModel().predict(forecast_input_data)

    # Estimate the stdev by using the stdev of the hour for historic_load
    model.confidence_interval = (
        data_with_features.groupby(data_with_features.index.hour)
        .std()
        .rename(columns=dict(load="stdev"))
    )

    # Apply confidence interval
    basecase_forecast = ConfidenceIntervalApplicatorBaseCase(
        model
    ).add_confidence_interval(basecase_forecast)

    # Do postprocessing
    basecase_forecast = add_prediction_job_properties_to_forecast(
        pj=pj,
        forecast=basecase_forecast,
        forecast_type=ForecastType.BASECASE,
        forecast_quality="not_renewed",
    )

    return basecase_forecast

# SPDX-FileCopyrightText: 2017-2021 Alliander N.V. <korte.termijn.prognoses@alliander.com> # noqa E501>
#
# SPDX-License-Identifier: MPL-2.0
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pandas as pd
import structlog

from openstf.validation import validation
from openstf.feature_engineering.feature_applicator import (
    OperationalPredictFeatureApplicator,
)
from openstf.model.confidence_interval_applicator import ConfidenceIntervalApplicator
from openstf.preprocessing import preprocessing
from openstf.model.serializer import PersistentStorageSerializer
from openstf.model.fallback import generate_fallback

MODEL_LOCATION = Path(".")

logger = structlog.get_logger(__name__)


def predict_pipeline(pj, input_data):
    """Computes the forecasts and confidence intervals given a prediction job and input data.


    Args:
        pj: (dict) prediction job
        input_data (pandas.DataFrame): data frame containing the input data necessary for the prediction.

    Returns:
        forecast (pandas.DataFrame)
    """
    # Get input data
    forecast_start, forecast_end = generate_forecast_datetime_range(
        resolution_minutes=pj["resolution_minutes"],
        horizon_minutes=pj["horizon_minutes"],
    )
    datetime_start, datetime_end = generate_inputdata_datetime_range(
        t_behind_days=14, t_ahead_days=3
    )

    # Get model
    model = PersistentStorageSerializer(pj).load_model()

    # Validate and clean data
    validated_data = validation.validate(input_data)

    # Add features
    data_with_features = OperationalPredictFeatureApplicator(
        horizons=[0.25], features=model._Booster.feature_names
    ).add_features(validated_data)

    # Prep forecast input
    forecast_input_data = data_with_features[forecast_start:forecast_end]

    # Check if sufficient data is left after cleaning
    if not validation.is_data_sufficient(data_with_features):
        fallback_strategy='extreme_day' # this can later be expanded
        logger.warning(
            "Using fallback forecast",
            forecast_type="fallback",
            pid=pj["id"],
            fallback_strategy=fallback_strategy
        )
        model_forecast = generate_fallback(forecast_input_data,
                                           input_data.iloc[:,[0]])

    else:
        # Predict
        model_forecast = model.predict(forecast_input_data.sort_index(axis=1))

    forecast = pd.DataFrame(
        index=forecast_input_data.index, data={"forecast": model_forecast}
    )

    # Add confidence
    forecast = ConfidenceIntervalApplicator(model).add_confidence_interval(
        forecast, pj["quantiles"]
    )

    # Prepare for output
    forecast = add_prediction_job_properties_to_forecast(
        pj,
        forecast,
    )

    return forecast


def add_prediction_job_properties_to_forecast(
    pj, forecast, forecast_type=None, forecast_quality=None
):
    # self.logger.info("Postproces in preparation of storing")
    if forecast_type is None:
        forecast_type = pj["typ"]
    else:
        # get the value from the enum
        forecast_type = forecast_type.value

    # NOTE this field is only used when making the babasecase forecast and fallback
    if forecast_quality is not None:
        forecast["quality"] = forecast_quality

    # TODO rename prediction job typ to type
    # TODO algtype = model_file_path, perhaps we can find a more logical name
    # TODO perhaps better to make a forecast its own class!
    # TODO double check and sync this with make_basecase_forecast (other fields are added)
    # !!!!! TODO fix the requirement for customer
    forecast["pid"] = pj["id"]
    forecast["customer"] = pj["name"]
    forecast["description"] = pj["description"]
    forecast["type"] = forecast_type
    forecast["algtype"] = pj["model"]

    return forecast


def generate_inputdata_datetime_range(t_behind_days=14, t_ahead_days=3):
    # get current date UTC
    date_today_utc = datetime.now(timezone.utc).date()
    # Date range for input data
    datetime_start = date_today_utc - timedelta(days=t_behind_days)
    datetime_end = date_today_utc + timedelta(days=t_ahead_days)

    return datetime_start, datetime_end


def generate_forecast_datetime_range(resolution_minutes, horizon_minutes):
    # get current date and time UTC
    datetime_utc = datetime.now(timezone.utc)
    # Datetime range for time interval to be predicted
    forecast_start = datetime_utc - timedelta(minutes=resolution_minutes)
    forecast_end = datetime_utc + timedelta(minutes=horizon_minutes)

    return forecast_start, forecast_end


def pre_process_input_data(input_data, flatliner_threshold):
    logger = structlog.get_logger(__name__)
    # Check for repeated load observations due to invalid measurements
    suspicious_moments = validation.find_nonzero_flatliner(
        input_data, threshold=flatliner_threshold
    )
    if suspicious_moments is not None:
        # Covert repeated load observations to NaN values
        input_data = preprocessing.replace_invalid_data(input_data, suspicious_moments)
        # Calculate number of NaN values
        # TODO should this not be part of the replace_invalid_data function?
        num_nan = sum([True for i, row in input_data.iterrows() if all(row.isnull())])
        logger.warning(
            "Found suspicious data points, converted to NaN value",
            num_nan_values=num_nan,
        )

    return input_data

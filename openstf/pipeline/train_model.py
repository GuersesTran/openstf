# SPDX-FileCopyrightText: 2017-2021 Alliander N.V. <korte.termijn.prognoses@alliander.com> # noqa E501>
#
# SPDX-License-Identifier: MPL-2.0
import logging
from pathlib import Path
from typing import List, Tuple, Union

import pandas as pd
import structlog
from openstf.dataclasses.model_specifications import ModelSpecificationDataClass
from openstf_dbc.services.prediction_job import PredictionJobDataClass

from openstf.exceptions import (
    InputDataInsufficientError,
    InputDataWrongColumnOrderError,
    OldModelHigherScoreError,
)
from openstf.feature_engineering.feature_applicator import TrainFeatureApplicator
from openstf.metrics.reporter import Report, Reporter
from openstf.model.model_creator import ModelCreator
from openstf.model.regressors.regressor import OpenstfRegressor
from openstf.model.serializer import PersistentStorageSerializer
from openstf.model.standard_deviation_generator import StandardDeviationGenerator
from openstf.model_selection.model_selection import split_data_train_validation_test
from openstf.validation import validation

DEFAULT_TRAIN_HORIZONS: List[float] = [0.25, 47.0]
MAXIMUM_MODEL_AGE: int = 7

DEFAULT_EARLY_STOPPING_ROUNDS: int = 10
PENALTY_FACTOR_OLD_MODEL: float = 1.2


def train_model_pipeline(
    pj: PredictionJobDataClass,
    input_data: pd.DataFrame,
    check_old_model_age: bool,
    trained_models_folder: Union[str, Path],
) -> None:
    """Midle level pipeline that takes care of all persistent storage dependencies

    Expected prediction jobs keys: "id", "model", "hyper_params",
        "feature_names"

    Args:
        pj (PredictionJobDataClass): Prediction job
        input_data (pd.DataFrame): Raw training input data
        check_old_model_age (bool): Check if training should be skipped because the model is too young
        trained_models_folder (Path): Path where trained models are stored

    Returns:
        None

    """
    # Intitialize logger and serializer
    logger = structlog.get_logger(__name__)
    serializer = PersistentStorageSerializer(trained_models_folder)

    # Get old model and age
    try:
        old_model, modelspecs = serializer.load_model(pj["id"])
        old_model_age = (
            old_model.age
        )  # Age attribute is openstf specific and is added by the serializer
    except FileNotFoundError:
        old_model = None
        old_model_age = float("inf")
        # create basic modelspecs
        modelspecs = ModelSpecificationDataClass(id=pj["id"])
        logger.warning("No old model found, training new model", pid=pj["id"])

    # Check old model age and continue yes/no
    if (old_model_age < MAXIMUM_MODEL_AGE) and check_old_model_age:
        logger.warning(
            f"Old model is younger than {MAXIMUM_MODEL_AGE} days, skip training"
        )
        return

    # Train model with core pipeline
    try:
        model, report, modelspecs_updated = train_model_pipeline_core(
            pj, modelspecs, input_data, old_model
        )
    except OldModelHigherScoreError as OMHSE:
        logger.error("Old model is better than new model", pid=pj["id"], exc_info=OMHSE)
        return

    except InputDataInsufficientError as IDIE:
        logger.error(
            "Input data is insufficient after validation and cleaning",
            pid=pj["id"],
            exc_info=IDIE,
        )
        raise InputDataInsufficientError(IDIE)

    except InputDataWrongColumnOrderError as IDWCOE:
        logger.error(
            "Wrong column order, 'load' column should be first and 'horizon' column last.",
            pid=pj["id"],
            exc_info=IDWCOE,
        )
        raise InputDataWrongColumnOrderError(IDWCOE)

    # Save model
    serializer.save_model(model, pj=pj, modelspecs=modelspecs_updated, report=report)

    # Clean up older models
    serializer.remove_old_models(pj=pj)


def train_model_pipeline_core(
    pj: PredictionJobDataClass,
    modelspecs: ModelSpecificationDataClass,
    input_data: pd.DataFrame,
    old_model: OpenstfRegressor = None,
    horizons: List[float] = None,
) -> Tuple[OpenstfRegressor, Report, ModelSpecificationDataClass]:
    """Train model core pipeline.
    Trains a new model given a prediction job, input data and compares it to an old model.
    This pipeline has no database or persistent storage dependencies.

    TODO once we have a data model for a prediction job this explantion is not
    required anymore.

    For training a model the following keys in the prediction job are
    expected:
        "id"            Only used for logging
        "model"         Model type, any of "xgb", "lgb",
    And in modelspecs:
        "hyper_params"  Hyper parameters dictionairy specific to the model_type
        "feature_names"      List of features to train model on or None to use all features

    Args:
        pj (PredictionJobDataClass): Prediction job
        modelspecs (ModelSpecificationDataClass): Dataclass containing model specifications
        input_data (pd.DataFrame): Input data
        old_model (OpenstfRegressor, optional): Old model to compare to. Defaults to None.
        horizons (List[float]): horizons to train on in hours.

    Raises:
        InputDataInsufficientError: when input data is insufficient.
        InputDataWrongColumnOrderError: when input data has a invalid column order.
        OldModelHigherScoreError: When old model is better than new model.

    Returns:
        Tuple[OpenstfRegressor, Report, ModelSpecificationDataClass]: Trained model and report (with figures)
    """

    if horizons is None:
        horizons = DEFAULT_TRAIN_HORIZONS

    logger = structlog.get_logger(__name__)

    # Call common pipeline
    model, report, train_data, validation_data, test_data = train_pipeline_common(
        pj, modelspecs, input_data, horizons
    )
    modelspecs.feature_names = list(train_data.columns)
    logging.info("Fitted a new model, not yet stored")

    # Check if new model is better than old model
    if old_model:
        combined = train_data.append(validation_data).reset_index(drop=True)
        x_data, y_data = (
            combined.iloc[:, 1:-1],
            combined.iloc[:, 0],
        )

        # Score method always returns R^2
        score_new_model = model.score(x_data, y_data)

        # Try to compare new model to old model.
        # If this does not success, for example since the feature names of the
        # old model differ from the new model, the new model is considered better
        try:
            score_old_model = old_model.score(x_data, y_data)

            # Check if R^2 is better for old model
            if score_old_model > score_new_model * PENALTY_FACTOR_OLD_MODEL:
                raise OldModelHigherScoreError(
                    f"Old model is better than new model for {pj['id']}."
                )

            logger.info(
                "New model is better than old model, continuing with training procces"
            )
        except ValueError as e:
            logger.info("Could not compare to old model", pid=pj["id"], exc_info=e)

    return model, report, modelspecs


def train_pipeline_common(
    pj: PredictionJobDataClass,
    modelspecs: ModelSpecificationDataClass,
    input_data: pd.DataFrame,
    horizons: List[float],
    test_fraction: float = 0.0,
    backtest: bool = False,
) -> Tuple[OpenstfRegressor, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Common pipeline shared with operational training and backtest training

    Args:
        pj (PredictionJobDataClass): Prediction job
        modelspecs (ModelSpecificationDataClass): Dataclass containing model specifications
        input_data (pd.DataFrame): Input data
        horizons (List[float]): horizons to train on in hours.
        test_fraction (float): fraction of data to use for testing
        backtest (bool): boolean if we need to do a backtest

    Returns:
        Tuple[RegressorMixin, Report, pd.DataFrame, pd.DataFrame, pd.DataFrame]: Trained model, report
         train_data, validation_data and test_data

    Raises:
        InputDataInsufficientError: when input data is insufficient.
        InputDataWrongColumnOrderError: when input data has a invalid column order.

    """
    if input_data.empty:
        raise InputDataInsufficientError("Input dataframe is empty")
    elif "load" not in input_data.columns:
        raise InputDataWrongColumnOrderError(
            "Missing the load column in the input dataframe"
        )
    # Validate and clean data
    validated_data = validation.clean(validation.validate(pj["id"], input_data))
    # Check if sufficient data is left after cleaning
    if not validation.is_data_sufficient(validated_data):
        raise InputDataInsufficientError(
            "Input data is insufficient, after validation and cleaning"
        )
    data_with_features = TrainFeatureApplicator(
        horizons=horizons, feature_names=modelspecs.feature_names
    ).add_features(validated_data)

    # Split data
    (
        peaks,
        peaks_val_train,
        train_data,
        validation_data,
        test_data,
    ) = split_data_train_validation_test(
        data_with_features,
        test_fraction=test_fraction,
        back_test=backtest,
    )

    # Test if first column is "load" and last column is "horizon"
    if train_data.columns[0] != "load" or train_data.columns[-1] != "horizon":
        raise InputDataWrongColumnOrderError(
            f"Wrong column order for {pj['id']} "
            "'load' column should be first and 'horizon' column last."
        )

    # Create relevant model
    model = ModelCreator.create_model(pj["model"], quantiles=pj["quantiles"])

    # split x and y data
    train_x, train_y = train_data.iloc[:, 1:-1], train_data.iloc[:, 0]
    validation_x, validation_y = (
        validation_data.iloc[:, 1:-1],
        validation_data.iloc[:, 0],
    )

    # Configure evals for early stopping
    eval_set = [(train_x, train_y), (validation_x, validation_y)]

    # Set relevant hyperparameters
    valid_hyper_parameters = {
        key: value
        for key, value in modelspecs.hyper_params.items()
        if key in model.get_params().keys()
    }

    model.set_params(**valid_hyper_parameters)
    model.fit(
        train_x,
        train_y,
        eval_set=eval_set,
        early_stopping_rounds=DEFAULT_EARLY_STOPPING_ROUNDS,
        verbose=False,
    )
    # Gets the feature importance df or None if we don't have feature importance
    model.feature_importance_dataframe = model.set_feature_importance()

    logging.info("Fitted a new model, not yet stored")

    # Do confidence interval determination
    model = StandardDeviationGenerator(
        validation_data
    ).generate_standard_deviation_data(model)

    # Report about the training process
    reporter = Reporter(train_data, validation_data, test_data)
    report = reporter.generate_report(model)

    return model, report, train_data, validation_data, test_data


def get_model_age(trained_models_folder: str, pid: int) -> float:
    """returns age of most recently trained model in days.
    If no previous model can be found, this returns float(inf).

    Args:
        trained_models_folder: str
        pid: int

    Returns:
        float: age of most recent model in days"""
    serializer = PersistentStorageSerializer(trained_models_folder)
    return serializer.determine_model_age_from_pid(pid)

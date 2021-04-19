# SPDX-FileCopyrightText: 2017-2021 Alliander N.V. <korte.termijn.prognoses@alliander.com> # noqa E501>
#
# SPDX-License-Identifier: MPL-2.0

""" This module contains all wheather related functions used for feature engineering.

"""
import numpy as np
import pandas as pd

# Set some (nameless) constants for the Antoine equation:
A = 6.116
M = 7.6
TN = 240.7
# Set some constants
TORR = 133.322368  # 1 torr = 133 Pa
# 1.168 is the mass of 1 m^3 of air on sea level with standard pressure.
D = 1.168


def calc_saturation_pressure(temperature):
    """Function that calculates the water vapour pressure from the temperature
    See https://www.vaisala.com/sites/default/files/documents/Humidity_Conversion_Formulas_B210973EN-F.pdf

    Args:
        Temperature (np.array): Temperature in C
    Returns:
        The saturation pressure of water at the respective temperature"""

    psat = A * 10 ** ((M * temperature) / (temperature + TN))
    return psat


def calc_vapour_pressure(rh, psat):
    """Calculates the vapour pressure

    Args:
        rh (np.ndarray or float): Relative humidity
        psat (np.ndarray or float): Saturation pressure: see calc_saturation_pressure
    Returns:
        The water vapour pressure"""
    return (rh) * psat


def calc_dewpoint(vapour_pressure):
    """Calculates the dewpoint

    Args:
        vapour_pressure (np.ndarray or float): The vapour pressure for which the dewpoint should be calculated
    Returns:
        dewpoint (np.ndarray or float):"""

    return TN / ((M / np.log10(vapour_pressure / A)) - 1)


def calc_air_density(temperature, pressure, rh):
    """Calculates the dewpoint

    Args:
        Temperature (np.ndarray or float): The temperature in C
        Pressure (np.ndarray or float): the atmospheric pressure in Pa
    Returns:
        Air density (np.ndarray or float): The air density (kg/m^3)"""

    # Calculate saturation pressure
    psat = calc_saturation_pressure(temperature)
    # Calculate the current vapour pressure
    vapour_pressure = calc_vapour_pressure(rh, psat)

    # Set tempareture to K
    temperature_k = temperature + 273.15

    # Calculate air density
    air_density = (
        D
        * (273.15 / temperature_k)
        * ((pressure - 0.3783 * vapour_pressure) / 760 / TORR)
    )

    return air_density


def add_humidity_features(data, feature_set_list=None):
    """Adds humidity features to the input dataframe.
    These features are calculated using functions defines in this module.
    A list of requested features is used to determine whether to add the humidity features or not.

    Args:
        data: (pd.DataFrame) input dataframe to which features have to be added
        feature_set_list: (list) list of requested features.

    Returns:
        pd.DataFrame, Same as input dataframe with extra columns for the humidty features.

    """

    # If feature_set_list is none add humidity feature anyway
    if feature_set_list is None:
        add_humidity_features = True

    # Otherwise check if they are among the reuqested features
    else:
        add_humidity_features = any(
            x
            in [
                "saturation_pressure",
                "vapour_pressure",
                "dewpoint",
                "air_density",
            ]
            for x in feature_set_list
        )

    # Check if any of the humidity features are requested and add them
    if add_humidity_features:
        # Try to add humidity  calculations, ignore if required columns are missing
        try:
            humidity_df = humidity_calculations(data.temp, data.humidity, data.pressure)
            data = data.join(humidity_df)
        except AttributeError:
            pass  # This happens when a required column for humidity_calculations
            # is not present

    return data


def humidity_calculations(temperature, rh, pressure):
    """Function that calculates the
    - Saturation pressure
    - Vapour pressure
    - Dewpoint
    - Air density
    Args:
        temperature (np.array): Temperature in C
        rh (np.array): Relative humidity in %
        pressure (np.array): The air pressure in hPa
    Returns:
        if the input is an np.ndarray: a pandas dataframe with the calculated moisture indices
        if the input is numeric: a dict with the calculated moisture indices"""

    # First: a sanity check on the relative humidity and the air pressure
    # We only check on the type of temperature, because they need to be the same anyway
    is_series = isinstance(temperature, (np.ndarray, pd.core.series.Series))
    is_scalar = isinstance(temperature, (float, int))

    if is_scalar is False and is_series is False:
        raise TypeError(
            "The input should be a pandas series or np.ndarry, or float or int"
        )

    # Suppres copy warnings
    with pd.option_context("mode.chained_assignment", None):
        if is_series:
            rh[rh > 1] = rh / 100  # This triggers copy warnings
            pressure[pressure < 80000] = np.nan  # This triggers copy warnings
        else:
            if rh > 1:
                rh /= 100
            if pressure < 80000:
                pressure = np.nan

    # If the input is a dataframe or np.ndarrays: return a dataframe
    if is_series:
        humidity_df = pd.DataFrame(
            columns=[
                "saturation_pressure",
                "vapour_pressure",
                "dewpoint",
                "air_density",
            ]
        )
        humidity_df["saturation_pressure"] = calc_saturation_pressure(temperature)
        humidity_df["vapour_pressure"] = calc_vapour_pressure(
            rh, humidity_df.saturation_pressure
        )
        humidity_df["dewpoint"] = calc_dewpoint(humidity_df.vapour_pressure)
        humidity_df["air_density"] = calc_air_density(temperature, pressure, rh)

        return humidity_df

    # Else: if the input is numeric: return a dict
    psat = calc_saturation_pressure(temperature)
    pw = calc_vapour_pressure(rh, psat)
    td = calc_dewpoint(pw)
    air_density = calc_air_density(temperature, pressure, rh)
    return {
        "saturation_pressure": psat,
        "vapour_pressure": pw,
        "dewpoint": td,
        "air_density": air_density,
    }


def calculate_windspeed_at_hubheight(windspeed, fromheight=10, hub_height=100):
    """
    function that extrapolates a wind from a certain height to 100m
    According to the wind power law (https://en.wikipedia.org/wiki/Wind_profile_power_law)

    input:
        - windspeed: float OR pandas series of windspeed at height = height
        - fromheight: height (m) of the windspeed data. Default is 10m
        - hubheight: height (m) of the turbine
    returns:
        - the windspeed at hubheight."""
    alpha = 0.143

    if not isinstance(windspeed, (np.ndarray, float, int, pd.core.series.Series)):
        raise TypeError(
            "The windspeed is not of the expected type!\n\
                        Got {}, expected np.ndarray, pd series or numeric".format(
                type(windspeed)
            )
        )

    try:
        if any(windspeed < 0):
            raise ValueError(
                "The windspeed cannot be negative, as it is the lenght of a vector"
            )
    except TypeError:
        if windspeed < 0:
            raise ValueError(
                "The windspeed cannot be negative, as it is the lenght of a vector"
            )
        windspeed = abs(windspeed)

    return windspeed * (hub_height / fromheight) ** alpha


def calculate_windturbine_power_output(windspeed, n_turbines=1, turbine_data=None):
    """This function calculates the generated wind power based on the wind speed.
    These values are related through the power curve, which is described by turbine_data.
    If no turbine_data is given, default values are used and results are normalized to 1MWp.
    If n_turbines=0, the result is normalized to a rated power of 1.

    Input:
        - windspeed: pd.DataFrame(index = datetime, columns = ["windspeedHub"])
        - nTurbines: int
        - turbineData: dict(slope_center, rated_power, steepness)

    Ouput:
        pd.DataFrame(index = datetime, columns = ["forecast"])"""

    if turbine_data is None:
        turbine_data = {
            "name": "Lagerwey L100",  # not used here
            "cut_in": 3,  # not used here
            "cut_off": 25,  # not used here
            "kind": "onshore",  # not used here
            "manufacturer": "Lagerwey",  # not used here
            "peak_capacity": 1,  # not used here
            "rated_power": 1,
            "slope_center": 8.07,
            "steepness": 0.664,
        }
    else:
        required_properties = ["rated_power", "steepness", "slope_center"]
        for prop in required_properties:
            if prop not in turbine_data.keys():
                raise KeyError(f"Required property '{prop}' not set in turbine data")

    generated_power = turbine_data["rated_power"] / (
        1
        + np.exp(
            -turbine_data["steepness"] * (windspeed - turbine_data["slope_center"])
        )
    )
    generated_power *= n_turbines

    return generated_power


def add_additional_wind_features(data, feature_set_list=None):
    """Adds additional wind features to the input data. These are calculated using the above functions

    Args:
        data: (pd.DataFrame) Dataframe to which the wind features have to be added
        feature_set_list: (list) List of requested features

    Returns:
        pd.DataFrame same as input dataframe with extra columns for the added wind features

    """
    if feature_set_list is None:
        add_additional_wind_features = True
    else:
        add_additional_wind_features = any(
            x
            in [
                "windspeed_100mExtrapolated",
                "windPowerFit_extrapolated",
                "windpowerFit_harm_arome",
            ]
            for x in feature_set_list
        )

    # Add add_additional_wind_features
    if "windspeed" in data.columns and add_additional_wind_features:
        data["windspeed_100mExtrapolated"] = calculate_windspeed_at_hubheight(
            data["windspeed"]
        )

        data["windPowerFit_extrapolated"] = calculate_windturbine_power_output(
            data["windspeed_100mExtrapolated"]
        )

    # Do extra check
    if "windspeed_100m" in data.columns and add_additional_wind_features:
        data["windpowerFit_harm_arome"] = calculate_windturbine_power_output(
            data["windspeed_100m"].astype(float)
        )

    return data
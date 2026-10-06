def calculate_emissions(activity_value, emission_factor):
    """
    Calculate greenhouse gas emissions.

    activity_value:
        Quantity of activity data, e.g. electricity in MWh.

    emission_factor:
        Emission factor corresponding to the activity.

    Returns:
        Emissions in tCO2e.
    """

    if activity_value is None:
        return 0

    if emission_factor is None:
        return 0

    if activity_value < 0:
        raise ValueError("Activity value cannot be negative.")

    if emission_factor < 0:
        raise ValueError("Emission factor cannot be negative.")

    return activity_value * emission_factor
def calculate_from_factor(activity_value, emission_factor):
    """
    Calculate emissions using an EmissionFactor database record.
    """

    if emission_factor is None:
        raise ValueError("Emission factor not found.")

    if not emission_factor.active:
        raise ValueError("Emission factor is inactive.")

    return calculate_emissions(
        activity_value,
        emission_factor.factor_value
    )
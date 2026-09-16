"""Validation Engine: enforces boundary checks, data-type coercion and required
fields for every BRSR metric before it is persisted."""


def validate_value(metric_def, raw_value):
    """
    Validate a raw form-submitted string against a metric's catalog definition.

    Returns (is_valid: bool, error_message: str|None, clean_value: str|None)
    clean_value is the normalized string safe to store in ESGData.value
    """
    data_type = metric_def.get("data_type", "text")
    required = metric_def.get("required", False)
    name = metric_def.get("name", metric_def.get("code"))

    if raw_value is None:
        raw_value = ""
    raw_value = str(raw_value).strip()

    if raw_value == "":
        if required:
            return False, f"'{name}' is required.", None
        return True, None, ""

    if data_type == "text":
        return True, None, raw_value

    if data_type == "yes_no":
        normalized = raw_value.strip().capitalize()
        if normalized not in ("Yes", "No"):
            return False, f"'{name}' must be Yes or No.", None
        return True, None, normalized

    if data_type in ("number", "percentage", "integer"):
        try:
            numeric = float(raw_value)
        except ValueError:
            return False, f"'{name}' must be a valid number.", None

        if data_type == "integer":
            if not numeric.is_integer():
                return False, f"'{name}' must be a whole number.", None
            numeric = int(numeric)

        min_val = metric_def.get("min", 0)
        max_val = metric_def.get("max")
        if data_type == "percentage":
            min_val = metric_def.get("min", 0)
            max_val = metric_def.get("max", 100)

        if min_val is not None and numeric < min_val:
            return False, f"'{name}' cannot be less than {min_val}.", None
        if max_val is not None and numeric > max_val:
            return False, f"'{name}' cannot be greater than {max_val}.", None

        return True, None, str(numeric)

    # Fallback: treat unknown types as free text
    return True, None, raw_value


def validate_batch(metric_defs_by_code, form_values):
    """
    Validate a dict of {metric_code: raw_value} against the catalog.
    Returns (errors: dict[code -> message], clean_values: dict[code -> str])
    """
    errors = {}
    clean_values = {}
    for code, raw_value in form_values.items():
        metric_def = metric_defs_by_code.get(code)
        if metric_def is None:
            continue
        ok, err, clean = validate_value(metric_def, raw_value)
        if not ok:
            errors[code] = err
        else:
            clean_values[code] = clean
    return errors, clean_values

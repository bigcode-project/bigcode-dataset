"""General utilities"""


def add_dict(dict1: dict, dict2: dict) -> None:
    """
    Add the values of dict2 to dict1. All values must be int, float or dictionaries that also verify this condition.
    Will modify dict1 and return None
    """
    for key, value in dict2.items():
        if isinstance(value, (int, float)):
            if key not in dict1:
                dict1[key] = 0
            dict1[key] += value
        elif isinstance(value, dict):
            if key not in dict1:
                dict1[key] = {}
            assert isinstance(dict1[key], dict)
            add_dict(dict1[key], value)
        else:
            raise ValueError(f"Invalid type for key/value {key}: {value}")

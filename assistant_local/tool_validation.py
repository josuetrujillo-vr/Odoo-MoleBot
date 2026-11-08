"""Validate model-proposed calls against a server-owned capability catalog."""


def validate_call(catalog, name, arguments):
    """Return validated arguments or reject any call outside the exact schema."""
    if not isinstance(name, str) or name not in catalog:
        raise ValueError("Unknown capability")
    schema = catalog[name]
    if not isinstance(arguments, dict) or arguments.keys() != schema.keys():
        raise ValueError("Invalid capability arguments")
    for key, rule in schema.items():
        if isinstance(rule, tuple) and len(rule) == 2 and callable(rule[1]):
            expected, check = rule
        else:
            expected, check = rule, None
        if isinstance(expected, (list, set)):
            if type(arguments[key]) not in expected:
                raise ValueError("Invalid capability argument type")
        elif isinstance(expected, tuple):
            if type(arguments[key]) is not expected:
                raise ValueError("Invalid capability argument type")
        elif type(arguments[key]) is not expected:
            raise ValueError("Invalid capability argument type")
        if check is not None and not check(arguments[key]):
            raise ValueError("Invalid capability argument value")
    return dict(arguments)

def normalize_float(value, min_value, max_value):
    try:
        value = float(value)
        return max(min(value, max_value), min_value)
    except ValueError:
        return min_value

def clamp(value, min_value, max_value):
    return max(min(value, max_value), min_value)

def map_range(value, in_min, in_max, out_min, out_max):
    return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
"""Acoustic physics shared by the detectors and the range engine."""


def speed_of_sound(temp_c=20.0):
    """m/s; linear approximation around 20 degC (+0.6 m/s per degC)."""
    return 343.0 + 0.6 * (float(temp_c) - 20.0)


def flash_to_bang_range_m(dt_s, temp_c=20.0):
    """Range implied by a flash->thunder delay."""
    return speed_of_sound(temp_c) * float(dt_s)


def bang_delay_s(range_m, temp_c=20.0):
    """Expected thunder delay for a strike at range_m."""
    return float(range_m) / speed_of_sound(temp_c)

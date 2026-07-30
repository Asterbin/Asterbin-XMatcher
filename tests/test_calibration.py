import numpy as np

from XMatcher.calibration import calibrate_two_theta


def test_calibrate_two_theta_applies_fixed_zero_shift():
    corrected = calibrate_two_theta([20.0, 40.0], zero_shift=0.12)

    assert corrected.tolist() == [20.12, 40.12]


def test_calibrate_two_theta_applies_angle_dependent_displacement_term():
    corrected = calibrate_two_theta([20.0, 80.0], specimen_displacement=0.2)

    np.testing.assert_allclose(corrected[0], 20.0 + 0.2 * np.cos(np.deg2rad(10.0)))
    assert corrected[0] - 20.0 > corrected[1] - 80.0

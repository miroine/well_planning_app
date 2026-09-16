"""Unit constants and conversions used at the UI/engine boundary."""
M2FT = 3.280839895
FT2M = 1.0 / M2FT
PSI_PER_FT_PER_PPG = 0.051948  # hydrostatic gradient factor ("0.052")
STEEL_PPG = 65.45
E_STEEL_PSI = 30.0e6
G_STEEL_PSI = 11.5e6
FT3_PER_BBL = 5.6146
M3_PER_BBL = 0.158987
GCC_TO_PPG = 8.3454


def hydrostatic_psi(ppg, tvd_ft):
    return PSI_PER_FT_PER_PPG * ppg * tvd_ft


def emw_ppg(p_psi, tvd_ft):
    return p_psi / (PSI_PER_FT_PER_PPG * max(tvd_ft, 1e-6))


def capacity_bbl_per_ft(d_in):
    return d_in ** 2 / 1029.4


def annular_capacity_bbl_per_ft(d_hole_in, d_pipe_in):
    return max(d_hole_in ** 2 - d_pipe_in ** 2, 0.0) / 1029.4

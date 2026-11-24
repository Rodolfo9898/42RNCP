"""The functions of the math library: "all functions of the math library" in a subject means every one of them."""

from __future__ import annotations

# Functions that only appear through well-known libraries named in "External Function".
# "All functions of the math library" means all of libm, so this is every function it exports
# (each also exists with an f and an l suffix), not only the common ones.
MATH_FUNCTIONS = [
    # Trigonometric and hyperbolic
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sincos",
    "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
    # Exponents, logarithms, powers and roots
    "exp", "exp2", "exp10", "expm1", "log", "log2", "log10", "log1p", "logb", "ilogb", "llogb",
    "pow", "pow10", "sqrt", "cbrt", "hypot",
    # Rounding, remainders and decomposition
    "ceil", "floor", "trunc", "round", "roundeven", "rint", "nearbyint",
    "lrint", "llrint", "lround", "llround", "fromfp", "fromfpx", "ufromfp", "ufromfpx",
    "fmod", "remainder", "drem", "remquo", "modf", "frexp", "ldexp",
    "scalb", "scalbn", "scalbln", "significand",
    # Sign, comparison and multiply-add
    "fabs", "copysign", "fdim", "fma", "fmin", "fmax", "fminmag", "fmaxmag",
    "fminimum", "fmaximum", "fminimum_num", "fmaximum_num", "fminimum_mag", "fmaximum_mag",
    "fminimum_mag_num", "fmaximum_mag_num",
    # Narrowing arithmetic
    "fadd", "fsub", "fmul", "fdiv", "fsqrt", "ffma", "dadd", "dsub", "dmul", "ddiv", "dsqrt", "dfma",
    # Special functions
    "erf", "erfc", "gamma", "lgamma", "lgamma_r", "lgammaf_r", "lgammal_r", "tgamma",
    "j0", "j1", "jn", "y0", "y1", "yn",
    # Floating-point representation
    "nan", "nextafter", "nexttoward", "nextup", "nextdown", "finite", "canonicalize",
    "getpayload", "setpayload", "setpayloadsig", "totalorder", "totalordermag", "matherr",
    # Complex numbers
    "cabs", "carg", "cimag", "creal", "conj", "cproj", "cexp", "clog", "clog10", "cpow", "csqrt",
    "csin", "ccos", "ctan", "casin", "cacos", "catan",
    "csinh", "ccosh", "ctanh", "casinh", "cacosh", "catanh",
    # Floating-point environment
    "feclearexcept", "fedisableexcept", "feenableexcept", "fegetenv", "fegetexcept",
    "fegetexceptflag", "fegetmode", "fegetround", "feholdexcept", "feraiseexcept", "fesetenv",
    "fesetexcept", "fesetexceptflag", "fesetmode", "fesetround", "fetestexcept",
    "fetestexceptflag", "feupdateenv",
]
